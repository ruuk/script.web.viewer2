# -*- coding: utf-8 -*-
"""
example renderer

moves infos from external stylesheet "css" to internal @style attributes 
and for debugging also in @title attributes.

adds css as text to html
"""
import cssutils
import os
import sys
import logging
import urlparse, re

cssutils.log.setLevel(logging.FATAL)
cssutils.log.raiseExceptions = False

# lxml egg may be in a lib dir below this file (not in SVN though)
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

def getDocument(html, css=None):
	"""
	returns a DOM of html, if css is given it is appended to html/body as 
	pre.cssutils
	"""
	try:
		from lxml import etree
	except ImportError, e:
		print 'You need lxml for this example:', e
	
	document = etree.HTML(html)
	if css:
		# prepare document (add css for debugging)
		e = etree.Element('pre', {'class': 'cssutils'})
		e.text = css
		document.find('body').append(e)
	return document

def getView(document, css):
	"""
	document
		a DOM document, currently an lxml HTML document
	css
		a CSS StyleSheet string
	
	returns style view
		a dict of {DOMElement: css.CSSStyleDeclaration} for html
	"""
	from lxml.cssselect import CSSSelector
	sheet = cssutils.parseString(css)
	
	view = {}
	specificities = {} # needed temporarily 

	# TODO: filter rules simpler?, add @media
	rules = (rule for rule in sheet if rule.type == rule.STYLE_RULE)	
	for rule in rules:
		for selector in rule.selectorList:
			#log(0, 'SELECTOR', selector.selectorText)
			# TODO: make this a callback to be able to use other stuff than lxml
			try:
				cssselector = CSSSelector(selector.selectorText)
			except:
				continue
			matching = cssselector.evaluate(document)
			
			for element in matching:
				#if element.tag in ('div',):
					# add styles for all matching DOM elements
					#log(1, 'ELEMENT', id(element), element.text)
					
					if element not in view:	
						# add initial empty style declatation
						view[element] = cssutils.css.CSSStyleDeclaration() # @UndefinedVariable
						specificities[element] = {}					
															
					for p in rule.style:
						# update style declaration
						if p not in view[element]:
							# setProperty needs a new Property object and
							# MUST NOT reuse the existing Property
							# which would be the same for all elements!
							# see Issue #23
							view[element].setProperty(p.name, p.value, p.priority)
							specificities[element][p.name] = selector.specificity
							#log(2, view[element].getProperty('color'))
							
						else:
							#log(2, view[element].getProperty('color'))
							sameprio = (p.priority == 
										view[element].getPropertyPriority(p.name))
							if not sameprio and bool(p.priority) or (
							   sameprio and selector.specificity >= 
											specificities[element][p.name]):
								# later, more specific or higher prio 
								view[element].setProperty(p.name, p.value, p.priority)
					

	return view

def getSoupView(soup, css, url=''):
	"""
	soup
		a BeautifulSoup 4 object
	css
		a CSS StyleSheet string
	
	returns style view
		a dict of tuples
	"""
	sheet = cssutils.parseString(css,href=url)
		
	cssutils.replaceUrls(sheet,lambda u: urlparse.urljoin(url, u), ignoreImportRules=True)
	view = {}
	specificities = {} # needed temporarily 

	# TODO: filter rules simpler?, add @media
	gens = []
	for i_rule in sheet:
		if i_rule.type == i_rule.IMPORT_RULE:
			cssutils.replaceUrls(i_rule.styleSheet,lambda u: urlparse.urljoin(i_rule.href, u), ignoreImportRules=True)
			rules = (rule for rule in i_rule.styleSheet if rule.type == rule.STYLE_RULE)
			gens.append(rules)
			
	rules = (rule for rule in sheet if rule.type == rule.STYLE_RULE)
	if gens:
		import itertools
		gens.append(rules)
		rules = itertools.chain(*gens)
	for rule in rules:
		for selector in rule.selectorList:
			#log(0, 'SELECTOR', selector.selectorText)
			# TODO: make this a callback to be able to use other stuff than lxml
			if ':' in selector.selectorText: continue #Ignore pseudo:classes because we can't use them, plus the match when we don't want them to on bs4
			matching = soup.select(selector.selectorText)
			for element in matching:
				ID = id(element)
				if ID not in view:
					# add initial empty style declatation
					view[ID] = (element,cssutils.css.CSSStyleDeclaration()) # @UndefinedVariable
					specificities[ID] = {}
														
				for p in rule.style:
					# update style declaration
					if p not in view[ID][1]:
						# setProperty needs a new Property object and
						# MUST NOT reuse the existing Property
						# which would be the same for all elements!
						# see Issue #23
						view[ID][1].setProperty(p.name, p.value, p.priority)
						specificities[ID][p.name] = selector.specificity
						#log(2, view[element].getProperty('color'))
						
					else:
						#log(2, view[element].getProperty('color'))
						sameprio = (p.priority == 
									view[ID][1].getPropertyPriority(p.name))
						if not sameprio and bool(p.priority) or (
						   sameprio and selector.specificity >= 
										specificities[ID][p.name]):
							# later, more specific or higher prio 
							view[ID][1].setProperty(p.name, p.value, p.priority)
					

	return view

def render2style(view):
	"""
	- add style into @style attribute
	- add style into @title attribute (for debugging)
	"""
	for element, style in view.items():
		v = style.getCssText(separator=u'')
		curr = element.get('style')
		if curr:
			element.set('style', ';'.join((curr,v)))
		else:
			element.set('style', v)
		#element.set('title', v)
		
def render2SoupStyle(view):
	"""
	- add style into @style attribute
	"""
	for element, style in view.values():
		v = style.getCssText(separator=u'')
		curr = element.get('style')
		if curr:
			element['style'] = ';'.join((curr,v))
		else:
			element['style'] = v

class CSSBackground:
	def __init__(self,style_dict):
		self.background = style_dict.get('background','')
		self.color = style_dict.get('background-color')
		image = style_dict.get('background-image')
		if image:
			test = urlRE.search(image)
			if test: image = test.group('url')
		self.image = image
		self.attachment = style_dict.get('background-attachment')
		self.repeat = style_dict.get('background-repeat')
		self.inheritPosition = False
		self.posX = None
		self.posY = None
		pos = style_dict.get('background-position')
		if pos:
			if pos == 'inherit':
				self.inheritPosition = True
			else:
				test = pos.split(' ')
				if len(test) > 1:
					self.posX , self.posY = test
				else:
					self.posX = pos
					self.posY = 'center'
		self._initialized = False
		
	def absPosX(self,width):
		if not self.posX: return 0
		posX = self.posX.replace('px','')
		if posX.endswith('%'):
			try:
				pct = int(posX[:-1])
			except:
				return None
			return int((pct/100.0) * width)
		
		try:
			return int(posX)
		except:
			return None
		
	def absPosY(self,height):
		if not self.posY: return 0
		posY = self.posY.replace('px','')
		if posY.endswith('%'):
			try:
				pct = int(posY[:-1])
			except:
				return None
			return int((pct/100.0) * height)
		
		try:
			return int(posY)
		except:
			return None
		
	def __nonzero__(self):
		return bool(self.image or self.color or self.background)
	
	def noInit(self):
		self.posX = self.posX or 0
		self.posY = self.posY or 0
		
	def init(self):
		if self._initialized: return
		self._initialized = True
		if not self.background: return self.noInit()
		if self.background == 'none': return self.noInit()
		if self.background == 'transparent': return self.noInit()
		bg = processCSSBackground(self.background)
		self.background = ''
		self.color = self.color or bg.get('color')
		self.image = self.image or bg.get('image')
		self.attachment = self.attachment or bg.get('attachment')
		self.repeat = self.repeat or bg.get('repeat')
		self.posX = self.posX or bg.get('posx',0)
		self.posY = self.posY or bg.get('posy',0)
		self.inheritPosition = self.inheritPosition or bg.get('pos_inherit')
		
	def xbmcColor(self):
		if not self.color: return
		if self.color.startswith('#'): return 'FF' + processColor(self.color[1:])
		return self.color.lower()

urlRE = re.compile('url\((?P<url>[^\)]*)\)')
numPosRE = re.compile('(-[\d]+%?)(?:px)?')
colorRE = re.compile('#\w+')
colorNameRE = re.compile('\w+')
attachmentRE = re.compile('scroll|fixed|inherit')
repeatRE = re.compile('repeat|repeat-x|repeat-y|no-repeat|inherit')
	
def processCSSBackground(bg):
	ret = {}
	for part in bg.split(' '):
		if colorRE.match(part):
			ret['color'] = part
			continue
		
		test = urlRE.match(part)
		if test:
			ret['image'] = test.group('url')
			continue
		
		if attachmentRE.match(part) and not 'attachment' in ret:
			ret['attachment'] = part
			continue
		
		if repeatRE.match(part) and not 'repeat' in ret:
			ret['repeat'] = part
			continue
		
		test = numPosRE.search(part)
		if test:
			if 'posx' in ret:
				ret['posy'] = test.group(1)
			else:
				ret['posx'] = test.group(1)
			continue
				
		if part in ('left','right'):
			ret['posx'] = part
			continue
		
		elif part in ('top','bottom'):
			ret['posy'] = part
			continue
		
		if part == 'center':
			if 'posx' in ret:
				ret['posy'] = part
			else:
				ret['posx'] = part
			continue
		
		if part == 'inherit':
			part['pos_inherit'] = True
		
		if colorNameRE.match(part) and not 'color' in ret:
			ret['color'] = part
	return ret

def processColor(color):
		color = color.strip()
		if len(color) == 3:
			color = color[0] + color[0] + color[1] + color[1] + color[2] + color[2]
		return color