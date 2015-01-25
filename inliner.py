import subprocess
import argparse
import os
import sys
import shutil
import magic
import re
import base64
import codecs
import jsbeautifier
import logging
import unicodedata
log = logging.getLogger('inliner')
log.setLevel(logging.INFO)
log.addHandler(logging.StreamHandler(sys.stderr))
import cssutils
cssutils.log.setLevel(logging.FATAL)
from bs4 import BeautifulSoup


re_link = re.compile("<link(.(?!>))*..")
re_meta = re.compile("<meta(.(?!>))*..")
re_url = re.compile("url\s*\(\s*[\"']?((.(?!ata:))+?)[\"']?\s*\)")

def expand_url_carriers(style_declaration, file_map):
    def replace(match):
        group1 = match.group(1)
        return ("url(data:%s;base64,%s)" % 
            (file_map[group1]['mime'], file_map[group1]['value'])) if (group1 != "" and group1 in file_map.keys()) else match.group(0)
    url_carriers = []
    url_carriers.append(style_declaration.getProperty('src'))
    url_carriers.append(style_declaration.getProperty('background'))
    url_carriers.append(style_declaration.getProperty('background-image'))
    url_carriers.append(style_declaration.getProperty('list-style-image'))
    for carrier in url_carriers:
        if carrier is not None:
            carrier.value = re.sub(re_url
                                   , replace
                                   , carrier.value)


def expand_css(file_map):
    log.info('\nExpanding stylesheets...')
    def expand_single_urls(stylesheet):
        for rule in stylesheet:
            if isinstance(rule, cssutils.css.CSSFontFaceRule) or isinstance(rule, cssutils.css.CSSStyleRule):
                expand_url_carriers(rule.style, file_map)

        return stylesheet

    def expand_single_import(stylesheet):
        imports = []
        for i, rule in enumerate(stylesheet):
            if isinstance(rule, cssutils.css.CSSImportRule):
                imports.append({'index': i, 'rule': rule})
        if len(imports) == 0:
            return expand_single_urls(stylesheet)
        else:
            for im in imports:
                deps = cssutils.parseString(file_map[im['rule'].href]['value'])
                for j, dep in enumerate(deps):
                    stylesheet.insertRule(dep, index=im['index']+j+1)
                stylesheet.deleteRule(im['index'])
            return expand_single_import(stylesheet)

    for key in file_map.keys():
        if file_map[key]['mime'] == "text/css":
            log.debug('- %s' % key)
            stylesheet = cssutils.parseString(file_map[key]['value'])
            stylesheet = expand_single_import(stylesheet)
            file_map[key]['value'] = stylesheet.cssText

def inline(soup, downloadDir, file_map):
    log.info('\nInlining resources...')

    def inline_style(style):
        style_declaration = cssutils.parseStyle(style)
        expand_url_carriers(style_declaration, file_map)
        return style_declaration.cssText
        
    def inline_script(script_tag):
        src = script_tag['src']
        if src in file_map.keys():
            type = "text/javascript"
            if 'type' in script_tag.attrs:
                type = script_tag['type']

            tag = soup.new_tag("script", type=type, _from=src)
            tag.append(soup.new_string(file_map[src]['value']))
            return tag        
        else:
            return script_tag

    def inline_link(link_tag):
        href = link_tag['href']

        if href is not None and href in file_map.keys():

            # NOTE: some file references, may not have been downloaded because
            # the containing class or element is not used in the html file
            # such file references will have 'absolute' paths, such as: http://cdn.foo.bar/img.jpg
            # and won't be touched here, as it doesn't matter anyways in terms of
            # correct display of the html page

            type = None
            if href.endswith('.js'):
                type = 'text/javascript'
            elif href.endswith('.css'):
                type = 'text/css'
            else:
                for ext in ['png', 'gif', 'jpg', 'jpeg']:
                    if href.endswith(ext):
                        type = ('image/%s' % ext)
                        break

            if type is None and (href.endswith('.ico') or ('type' in link_tag.attrs and link_tag['type'] == 'image/x-icon')):
                type = 'image/x-icon'

            if type is None and 'type' in link_tag.attrs:
                type = link_tag['type']

            if type is None and 'rel' in link_tag.attrs and link_tag['rel'] == u'stylesheet':
                type = "text/css"

            if type is None:
                return link_tag
                
            tag = None
            if type is not None and 'css' in type:
                tag = soup.new_tag("style", type=type, _from=href)
                tag.append(soup.new_string(file_map[href]['value']))
            elif type is not None and 'image' in type:
                tag = soup.new_tag("link", type=type, _from=href, href="data:%s;base64,%s" % (file_map[href]['mime'], file_map[href]['value']))
            else:
                tag = soup.new_tag("script", type=type, _from=href)
                tag.append(soup.new_string(file_map[href]['value']))
            
            return tag
        else:
            return link_tag

    def inline_video(video_tag):
        src = video_tag['src']
        sources = video_tag.find_all('source')
        if src is not None and src != "" and src in file_map.keys():
            video_tag['src'] = "data:%s;base64,%s" % (file_map[src]['mime'], file_map[src]['value'])
            video_tag['_from'] = src
        elif sources != []:
            for source in sources:
                src = source['src'].strip()
                if src in file_map.keys():
                    mime = source['type'] if 'type' in source.attrs else file_map[src]['mime']
                    source['src'] = "data:%s;base64,%s" % (mime, file_map[src]['value'])
                    source['_from'] = src
        return video_tag

    def inline_img(img_tag):
        src = img_tag['src']
        if src in file_map.keys():
            tag = soup.new_tag("img", _from=src, src=("data:%s;base64,%s" % (file_map[src]['mime'], file_map[src]['value'])))
            return tag
        else:
            log.debug('Omitting resource %s' % src)
            return img_tag

    for tag in soup.find_all(lambda tag: "style" in tag.attrs and tag['style'] is not None):
        tag['style'] = inline_style(tag['style'])

    for tag in soup.find_all(lambda tag: "script" == tag.name and "src" in tag.attrs and tag['src'] is not None):
        tag.replaceWith(inline_script(tag))

    for tag in soup.find_all(lambda tag: "link" == tag.name and "href" in tag.attrs and tag['href'] is not None):
        tag.replaceWith(inline_link(tag))

    for tag in soup.find_all(lambda tag: "img" == tag.name and "src" in tag.attrs and tag['src'] is not None):
        tag.replaceWith(inline_img(tag))

    for tag in soup.find_all(lambda tag: "video" == tag.name):
        tag.replaceWith(inline_video(tag))

    return soup


def main():
    def parse_args():
        parser = argparse.ArgumentParser()
        parser.add_argument('-u', '--uri', help='The URI to download and inline', required=True)
        parser.add_argument('-d', '--dir', help='The local folder where retrieved data will be stored', required=True)
        parser.add_argument('-i', '--inline', help='Inline the file of specified name from the local directory. If not specified, inliner will try to find the file automagically', required=False)
        parser.add_argument('-l', '--local', action='store_true', default=False, help='Use content from local directory, do not download data', required=False)
        parser.add_argument('-p', '--prettify', action='store_true', default=False, help='Prettify javscript', required=False)
        parser.add_argument('-ni', '--no-images', action='store_true', default=False, help='Don\'t embed images', required=False)
        parser.add_argument('-nf', '--no-fonts', action='store_true', default=False, help='Don\'t embed fonts', required=False)
        parser.add_argument('-nv', '--no-videos', action='store_true', default=False, help='Don\'t embed videos', required=False)
        parser.add_argument('-v', '--verbose', action='store_true', default=False, help="verbose output", required=False)
        return parser.parse_args()

    def assert_wget_installed():
        try:
            subprocess.check_output(['wget', '--version'])
        except OSError:
            log.critical("please install wget\n")
            sys.exit(1)

    def prepare_download_dir(path):
        try:
            os.stat(path)
            if os.path.isdir(path):
                while True:
                    log.info('\nDirectory %s exists.' % os.path.join(os.getcwd(),path))
                    log.info ('All content will be deleted. Do you want to continue? [y/n]')
                    input = sys.stdin.readline()
                    if input == 'n\n' or input == 'no\n':
                        sys.exit(0)
                    if input == 'y\n' or input == 'yes\n':
                        break
                shutil.rmtree(path)
                os.mkdir(path)
            else:
                log.critical ('%s is an existing file. Cowardly refusing to delete... goodbye\n')
                sys.exit(0)
        except OSError:
            os.mkdir(path)

    def run_wget(uri, dir):
        try:
            log.info("\nNow downloading files. Please wait...")
            process = subprocess.Popen(['wget', '-p', '-k', '-nd', '-H',  '-P', dir, uri], stderr=subprocess.PIPE)
            for line in iter(process.stderr.readline, ''):
                log.debug(line[:-1])
        except OSError:
            log.critical ("Error wgetting files.\n")
            sys.exit(1)


    def build_resource_map(downloaddir, inline_file=False, local=False, no_images=False, no_fonts=False, no_videos=False, prettify=False):
        def read_text_file(file):
            try:
                return codecs.open(path, 'r', 'utf-8').read(), 'utf-8'
            except:
                return codecs.open(path, 'r', 'iso-8859-1').read(), 'iso-8859-1'

        def fix_script_strings(s):
            re_scr_str = re.compile("</script>")
            return re.sub(re_scr_str, lambda match: "</' + 'cript>", s)

        def get_mime(file):
            if file.endswith('.js'):
                return "text/javascript"
            elif file.endswith('.html') or file.endswith('.xhtml'):
                return "text/html"
            elif file.endswith('.css'):
                return "text/css"
            else:
                return magic.from_file(file, mime=True)

        htmlsoup = None
        file_map = {}
        htmlfile = None
        htmlencoding = None

        log.info("\nBuilding resource map...")
        log.debug("==========================================")

        # loop files, find base html file, b64 encode images
        for file in (unicodedata.normalize('NFC', f) for f in os.listdir(unicode(downloaddir))): 

            path = os.path.join(downloaddir, file)
            mime = get_mime(path)

            log.debug('- %s [%s]' % (file, mime))
            if file == inline_file:
                maybe_html,htmlenconding = read_text_file(file)
                soup = BeautifulSoup(maybe_html)
                if soup.html is None:
                    log.critical("The file specified by -f does not seem to be an html file. Aborting.")
                    sys.exit(1)
                else:
                    htmlsoup = soup
                    continue

            if 'text/' in mime:
                maybe_html,encoding = read_text_file(file)
                soup = BeautifulSoup(maybe_html)

                if soup.html is not None:
                    if htmlfile is None or file == 'index.html': # index.html takes precedence
                        htmlfile = file
                        htmlencoding = encoding
                        # ok it is html, but often people do not close their link and meta tags
                        # which leads to malformed header data in soap - let's fix that
                        html = re.sub(re_link, lambda match: match.group(0).strip() if match.group(0).strip().endswith("/>") else match.group(0).strip()[:-1] + "/>", maybe_html)
                        html = re.sub(re_meta, lambda match: match.group(0).strip() if match.group(0).strip().endswith("/>") else match.group(0).strip()[:-1] + "/>", html)
                        htmlsoup = BeautifulSoup(html)

                if 'javascript' in mime or file.endswith('.js'):
                    fixed = fix_script_strings(maybe_html)
                    file_map[file] = {'value': jsbeautifier.beautify(fixed) if prettify else fixed, 'mime': mime}
                else:
                    file_map[file] = {'value': maybe_html, 'mime': mime}


            if 'image/' in mime and not no_images:
                image = open(path, 'r')
                file_map[file] = {'value': base64.b64encode(image.read()), 'mime': mime}

            if 'video/' in mime and not no_videos:
                video = open(path, 'r')
                file_map[file] = {'value': base64.b64encode(video.read()), 'mime': mime}

            elif not no_fonts:
                font_extensions = ['.eot', '.eot?', '.ttf', '.ttf?', '.woff', '.woff?']
                for ext in font_extensions:
                    if file.endswith(ext):
                        font = open(path, 'r')
                        file_map[file] = {'value': base64.b64encode(font.read()), 'mime': mime}
                        break

        if htmlfile is not None:
            log.info("\nUsing %s" % htmlfile) 

        return htmlsoup, htmlencoding, file_map


    # make sure wget is installed wget is used to download a webpage 
    # into a flat filestructure within a local folder while
    # automatically converting the links/references accordingly
    assert_wget_installed()


    # get command line arguments
    args = parse_args()
    uri = args.uri
    downloaddir = args.dir
    inline_file = args.inline
    local = args.local
    no_images = args.no_images
    no_fonts = args.no_fonts
    no_videos = args.no_videos
    prettify = args.prettify
    verbose = args.verbose


    if verbose:
        log.setLevel(logging.DEBUG)

    if not local:
        prepare_download_dir(downloaddir)
        run_wget(uri, downloaddir)

    htmlsoup, encoding, file_map = build_resource_map(downloaddir, inline_file=inline_file, local=local, no_images=no_images, no_fonts=no_fonts, no_videos=no_videos, prettify=prettify)


    if htmlsoup is not None:
        expand_css(file_map)                
        soup = inline (htmlsoup, downloaddir, file_map)

        print(soup.prettify().encode(encoding))

    else:
        log.critical("\nCould not find any html file to inline in folder: %s\n" % downloaddir)
        sys.exit(1)

if __name__ == '__main__':
    main()

