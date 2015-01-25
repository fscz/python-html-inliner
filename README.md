# python-html-inliner
python-html-inliner downloads a webpage into a local folder and subsequently produces a single html file with styles, fonts, scripts, images, videos inlined.


# Dependencies
In order to use python-html-inliner you need [Python 2](https://docs.python.org/2/), [wget](https://www.gnu.org/software/wget/) and the following python packages. Install them with pip.

 * [cssutils](https://pypi.python.org/pypi/cssutils/)
 * [jsbeautifier](https://github.com/beautify-web/js-beautify)
 * [beautifulsoup4](http://www.crummy.com/software/BeautifulSoup/)
 * [python-magic](https://github.com/ahupp/python-magic)


# Usage
usage: inliner.py [-h] -u URI -d DIR [-i INLINE] [-l] [-p] [-ni] [-nf] [-nv]
                  [-v]

optional arguments:

  * -h, --help            
  
  show this help message and exit
  * -u URI, --uri URI     
  
  The URI to download and inline
  * -d DIR, --dir DIR
  
  The local folder where retrieved data will be stored
  * -i INLINE, --inline INLINE
  
  Inline the file of specified name from the local
  directory. If not specified, inliner will try to find
  the file automagically
  * -l, --local           
  
  Use content from local directory, do not download data
  * -p, --prettify    
  
  Prettify javscript
  * -ni, --no-images  
  
  Don't embed images
  * -nf, --no-fonts  
  
  Don't embed fonts
  * -nv, --no-videos  
  
  Don't embed videos
  * -v, --verbose         
  
  verbose output


# Examples
Here are a few examples, how you might want to use python-html-inliner.

* python inliner.py  -d tmp -u http://factis.de --prettify --verbose  > factis.html
* python inliner.py  -d tmp -u http://factis.de/jobs --prettify --verbose  > factis.html
* python inliner.py  -d tmp -u http://wikipedia.org  > wikipedia.html

Once you have a local folder with all the files you need, you can work locally, with the --local option.

* python inliner.py  -d tmp -u http://wikipedia.org  > wikipedia.html
* python inliner.py  -d tmp -u http://wikipedia.org  --local --no-images --no-fonts > wikipedia.html

Here you can see some results:

* [https://www.factis.de/](https://cdn.rawgit.com/fscz/python-html-inliner/master/examples/factis.html)
* [https://www.factis.de/jobs](https://cdn.rawgit.com/fscz/python-html-inliner/master/examples/jobs.html)
* [http://http://www.lohmann-birkner.de/en/index.php](https://cdn.rawgit.com/fscz/python-html-inliner/master/examples/lub.html)
* [https://www.python.org/](https://cdn.rawgit.com/fscz/python-html-inliner/master/examples/python.html)