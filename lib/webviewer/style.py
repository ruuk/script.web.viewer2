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
import urlparse

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
						view[element] = cssutils.css.CSSStyleDeclaration()
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
			matching = soup.select(selector.selectorText)
# 			if 'border' in selector.selectorText and matching:
# 				print selector.selectorText,rule.style.getCssText(separator=u'')
# 				for m in matching:
# 					print '%s %s' % (id(m),m.get('class'))
# 			elif 'border' in selector.selectorText:
# 				print '-------'
# 				print selector.selectorText
# 				print rule.style.getCssText(separator=u'')
# 				print '-------'
			for element in matching:
				ID = id(element)
				if ID not in view:
					# add initial empty style declatation
					view[ID] = (element,cssutils.css.CSSStyleDeclaration())
					specificities[ID] = {}
					#if 'img' in selector.selectorText: print '%s %s' % (id(element),element)		
														
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
		#if element.name.startswith('b'): print v
		#if element.name == 'img' and 'player' in element.get('src','').lower(): print u'{0} {1} {2}'.format(id(element), element.get('src'), v)
		curr = element.get('style')
		if curr:
			element['style'] = ';'.join((curr,v))
		else:
			element['style'] = v

