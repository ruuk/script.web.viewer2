import re, htmlentitydefs, chardet

def cUConvert(m): return unichr(int(m.group(1)))
def cTConvert(m): return unichr(htmlentitydefs.name2codepoint.get(m.group(1),32))
def convertHTMLCodes(html,encoding=None):
	html, detected_encoding = getUnicode(html, encoding)
	try:
		html = re.sub('&#(\d{1,5});',cUConvert,html)
		html = re.sub('&(\w+?);',cTConvert,html)
	except:
		pass
	return (html,detected_encoding)

def getUnicode(html,encoding=None):
	detected_encoding = None
	if not isinstance(html,unicode):
		if not encoding:
			encoding = 'UTF-8'
		try:
			html = unicode(html,encoding)
		except:
			detected_encoding = chardet.detect(html)
			try:
				html = unicode(html,detected_encoding['encoding'])
			except:
				html = unicode(html,encoding,'replace')
				
	return (html,detected_encoding)