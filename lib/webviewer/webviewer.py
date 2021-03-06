import xbmc, xbmcgui, xbmcaddon
import os, sys, textwrap, codecs, urlparse, re, time, math, urllib2
from xml.sax.saxutils import escape as escapeXML
import htmldecode, mechanize, fontmanager, video, bs4, xbmcutil, style, imageops
from webimage import imageinfo, threadpool
from xbmcconstants import * # @UnusedWildImport

ADDON = xbmcaddon.Addon('script.web.viewer2')
T = ADDON.getLocalizedString

THEME = 'Default'

LOG_PREFIX = 'WebViewer 2'

ADDON_DATA_DIR = xbmc.translatePath(ADDON.getAddonInfo('profile'))
CACHE_PATH = os.path.join(ADDON_DATA_DIR,'cache')
if not os.path.exists(CACHE_PATH): os.makedirs(CACHE_PATH)

def LOG(message):
	print '%s: %s' % (LOG_PREFIX,message)
	
def ERROR(message,hide_tb=False):
	LOG('ERROR: ' + message)
	short = str(sys.exc_info()[1])
	if hide_tb:
		LOG('ERROR Message: ' + short)
	else:
		import traceback
		traceback.print_exc()
	return short

class ResponseData:
	def __init__(self, url='', content='', data='', content_disp='',response=None):
		self.url = url
		self.content = content
		self.contentDisp = content_disp
		self.data = data
		self.response = response
		self.forms = []
		self.ID = None
		
	def hasText(self):
		return self.content.startswith('text') and self.data

class WebReader:
	def __init__(self):
		cookiesPath = os.path.join(ADDON_DATA_DIR,'cookies')
		LOG('Cookies will be saved to: ' + cookiesPath)
		cookies = mechanize.LWPCookieJar(cookiesPath)
		if os.path.exists(cookiesPath): cookies.load()
		self.cookieJar = cookies
		opener = mechanize.build_opener(mechanize.HTTPCookieProcessor(cookies))
		mechanize.install_opener(opener)
		self.browser = mechanize.Browser()
		self.browser.set_cookiejar(self.cookieJar)
		self.browser.set_handle_robots(False)
		self.browser.set_handle_redirect(True)
		self.browser.set_handle_refresh(True, honor_time=False)
		self.browser.set_handle_equiv(True)
		self.browser.set_debug_redirects(True)
		self.browser.addheaders = [('User-agent', 'Mozilla/3.0 (compatible)'), ('Accept', '*/*')]
		#self.browser.addheaders = [('User-agent','Mozilla/5.0 (X11; Linux i686; rv:2.0.1) Gecko/20100101 Firefox/4.0.1')]
		self.frameFilter = re.compile('<i?frame[^>]*?src="(?P<url>[^>"]+?)"[^>]*?>(?:.*?</iframe>)?',re.I)
		self.titleAttrFilter = re.compile('title="([^>"]*?)"',re.I)
		self.nameAttrFilter = re.compile('name="([^>"]*?)"',re.I)
		self.linkFilter = re.compile('<(?:a|embed)[^>]+?(?:href|src)=["\'](?P<url>[^>"]+?)["\'][^>]*?(?:title=["\'](?P<title>[^>"]+?)["\'][^>]*?)?>(?P<text>.*?)</(?:a|embed)>',re.I|re.S|re.U)
		self.imageFilter = re.compile('<img[^>]+?src=["\'](?P<url>[^>"]+?)["\'][^>]*?>',re.I|re.S|re.U)
		self.srcFilter = re.compile('src=["\'][^"\']+?["\']')
		self.hrefFilter = re.compile('href=["\'][^"\']+?["\']')
		self.frameFixBaseURL = ''
		self.framesList = []

	def setBrowser(self,browser):
		LOG('Using Alternate Browser')
		self.browser = browser
		
	def saveCookies(self):
		if self.cookieJar is not None:
			self.cookieJar.save()
			
	def handleFile(self,url):
		try:
			with open(url[7:],'r') as f:
				data = f.read()
		except:
			ERROR('Failed To Open File',hide_tb=True)
			return None
		return ResponseData(url,'text/html',data)
			
	def getWebPage(self, url, callback=None):
		if url.startswith('file://'): return self.handleFile(url)
		LOG('Getting Page at URL: ' + url)
		if not callback: callback = self.fakeCallback
		resData = ResponseData(url)
		ID = ''
		urlsplit = url.split('#', 1)
		if len(urlsplit) > 1: url, ID = urlsplit
		try:
			resData = self.readURL(url, callback)
		except:
			err = ERROR('ERROR READING PAGE')
			LOG('URL: %s' % url)
			xbmcgui.Dialog().ok('ERROR', T(32100), err)
			return None
		resData = self.checkRedirect(resData, callback)
		if not callback(80, T(32101)): return None
		if not resData: return None
		formsProcessed = True
		forms = []
		if resData.hasText():
			try:
				forms = self.browser.forms()
			except:
				formsProcessed = False
			if not formsProcessed:
				try:
					res = self.browser.response()
					res.set_data(self.cleanHTML(res.get_data()))
					self.browser.set_response(res)
					forms = self.browser.forms()
				except:
					ERROR('Could not process forms')
		if not resData: return None
		resData.ID = ID
		resData.forms = forms or []
		self.saveCookies()
		return resData
	
	def cleanHTML(self, html):
		return re.sub('<![^>]*?>', '', html)
		
	def checkRedirect(self, resData, callback=None):
		if not callback: callback = self.fakeCallback
		match = re.search('<meta[^>]+?http-equiv="Refresh"[^>]*?URL=(?P<url>[^>"]+?)"[^>]*?/>', resData.data)
		#print html
		if match:
			LOG('REDIRECTING TO %s' % match.group('url'))
			if not callback(3, T(32102)): return None
			try:
				url = match.group('url')
				return self.readURL(url, callback)
			except:
				#err = 
				ERROR('ERROR READING PAGE REDIRECT')
				LOG('URL: %s' % url)
				#xbmcgui.Dialog().ok('ERROR','Error loading page.',err)
		return resData
	
	def readURL(self, url, callback):
		if not callback(5, T(32103)): return None
		response = None
		try:
			response = self.browser.open(url)
		except Exception, e:
			#If we have a redirect loop, this is a same url cookie issue. Just use the response in the error.
			if 'redirect' in str(e) and 'infinite loop' in str(e):
				response = e
			else:
				raise
		content = response.info().get('content-type', '')
		contentDisp = response.info().get('content-disposition', '')
		#print response.info()
		if not content.startswith('text'): return ResponseData(response.geturl(), content, content_disp=contentDisp,response=response)
		if not callback(30, T(32104)): return None
		html = response.read()
		if ADDON.getSetting('inline_frames') == 'true':
			self.framesList = []
			html = self.frameFilter.sub(self.frameLoader,html)
			for f in self.framesList: html = html.replace('</html>','<br />--FRAME' + ('-'*200) + '<br />'+ f + '<br />' + ('-'*200) + '<br /></html>')
			response.set_data(html)
			self.browser.set_response(response)
		return ResponseData(response.geturl(), content, html)
		
	def frameLoader(self,m):
		try:
			url = m.group('url')
			html = self.readURL(url, self.fakeCallback).data
			html = self.fixFramePaths(html, url)
			title = ''
			title_m = self.titleAttrFilter.search(m.group(0))
			if not title_m:
				title_m = self.nameAttrFilter.search(m.group(0))
			if title_m: title = ':%s' % title_m.group(1)
			html = html.replace('<html>','').replace('</html>','')
			html = re.split('<body[^>]*?>',html,1)[-1].split('</body>')[0]
			if ADDON.getSetting('frames_at_end') == 'true':
				self.framesList.append(html)
				return ''
			else:
				return '<br />--FRAME' + title.replace(' ','_') + ('-'*200) + '<br />'+ html + '<br />' + ('-'*200) + '<br />'
		except:
			ERROR('Failed to load frame inline')
			return m.group(0)
	
	def fixFramePaths(self,html,url):
		self.frameFixBaseURL = url
		html = self.imageFilter.sub(self.fixFrameImages,html)
		html = self.linkFilter.sub(self.fixFrameLinks,html)
		return html
	
	def fixFrameImages(self,m):
		url = m.group('url')
		full = urlparse.urljoin(self.frameFixBaseURL,url)
		ret = self.srcFilter.sub('src="%s"' % full,m.group(0))
		return ret
	
	def fixFrameLinks(self,m):
		url = m.group('url')
		full = urlparse.urljoin(self.frameFixBaseURL,url)
		ret = self.srcFilter.sub('src="%s"' % full,m.group(0))
		ret = self.hrefFilter.sub('href="%s"' % full,ret)
		#print m.group(0)
		#print ret
		return ret
	
	def submitFormOld(self, form, submit_control, callback):
		if not callback: callback = self.fakeCallback
		self.browser.form = form
		ct = 0
		if submit_control:
			for c in form.controls:
				if c.type == 'submit':
					if c == submit_control: break
					ct += 1 
		if not callback(5, T(32105)): return None
		try:
			res = self.browser.submit(nr=ct)
		except:
			self.browser.back()
			return None
		if not callback(60, T(32106)): return None
		html = res.read()
		resData = self.checkRedirect(ResponseData(res.geturl(), data=html), callback=callback) #@UnusedVariable
		if not callback(80, T(32101)): return None
		if not resData: return None
		resData.forms = resData.data and self.browser.forms() or []
		return resData
		
	def submitForm(self,form_idx,submit_idx,control_tags=None):
		self.browser.select_form(nr=form_idx)
		if control_tags:
			for t in control_tags:
				name = t.get('name')
				if not name: continue
				if t.get('type') == 'submit': continue
				control = self.browser.form.find_control(name)
				#print '%s: %s' % (control.type, control.name)
				if control.type in ('text','textarea','password','email'):
					if not control.readonly:
						if t.name == 'textarea':
							val = t.string
						else:
							val = t.get('value','')
						self.browser[name] = val
				elif control.type == 'select':
					idx = 0
					for opt in t.contents:
						if hasattr(opt,'name') and opt.name == 'option':
							if opt.get('disabled') == None:
								control.items[idx].selected = opt.get('selected') != None and True or False
							idx+=1
		try:
			res = self.browser.submit(nr=submit_idx)
		except:
			ERROR('Submit Failed',hide_tb=True)
			self.browser.back()
			return None
		html = res.read()
		content = res.info().get('content-type', '')
		resData = self.checkRedirect(ResponseData(res.geturl(), content, data=html))
		if not resData: return None
		resData.forms = resData.data and self.browser.forms() or []
		self.saveCookies()
		return resData
		
	def setFormValue(self,form,key,value):
		self.browser.form = form
		try:
			self.browser[key] = value
			return True
		except:
			return False
		
	def getForm(self, html, action, name=None):
		if not action: return None
		try:
			forms = self.mechanize.ParseString(''.join(re.findall('<form\saction="%s.+?</form>' % re.escape(action), html, re.S)), self._url)
			if name:
				for f in forms:
					if f.name == name:
						return f
			for f in forms:
				if action in f.action:
					return f
			LOG('NO FORM 2')
		except:
			ERROR('PARSE ERROR')
		
	def fakeCallback(self, pct, message=''): return True
						
	def doForm(self, url, form_name=None, action_match=None, field_dict={}, controls=None, submit_name=None, submit_value=None, wait='1', callback=None):
		if not callback: callback = self.fakeCallback
		if not self.checkLogin(callback=callback): return False
		res = self.browser.open(url)
		html = res.read()
		selected = False
		try:
			if form_name:
				self.browser.select_form(form_name)
				LOG('FORM SELECTED BY NAME')
			else:
				predicate = lambda formobj: action_match in formobj.action
				self.browser.select_form(predicate=predicate)
				LOG('FORM SELECTED BY ACTION')
			selected = True
		except:
			ERROR('NO FORM 1')
			
		if not selected:
			form = self.getForm(html, action_match, form_name)
			if form:
				self.browser.form = form
			else:
				return False
		try:
			for k in field_dict.keys():
				if field_dict[k]: self.browser[k] = field_dict[k]
			self.setControls(controls)
			wait = int(wait)
			time.sleep(wait) #or this will fail on some forums. I went round and round to find this out.
			res = self.browser.submit(name=submit_name, label=submit_value)
		except:
			ERROR('FORM ERROR')
			return False
			
		return True
		
	def setControls(self, controls):
		if not controls: return
		x = 1
		for control in controls:
			ctype, rest = control.split(':', 1)
			ftype, rest = rest.split('.', 1)
			name, value = rest.split('=')
			control = self.browser.find_control(**{ftype:name})
			if ctype == 'radio':
				control.value = [value]
			elif ctype == 'checkbox':
				control.items[0].selected = value == 'True'
			x += 1

class HistoryLocation:
	def __init__(self, url='', line=0, title='',render_file=None):
		self.url = url
		self.line = line
		self.title = title
		self.renderFile = render_file
		
	def __str__(self):
		return '<HistoryLocation (url: {0} title: {1} line: {2})>'.format(self.url,self.title,self.line)
	
	def __repr__(self):
		return self.__str__()
	
	def getTitle(self):
		return self.title or self.url
	
	def setRenderFile(self,render_file):
		pass
	
	def copy(self, other):
		if other.url: self.url = other.url
		if other.title: self.title = other.title
		self.line = other.line
		
class URLHistory:
	def __init__(self, first):
		self.index = 0
		self.history = [first]
		
	def addURL(self, new, old=None):
		if old: self.history[self.index].copy(old) 
		self.history = self.history[0:self.index + 1]
		self.history.append(new)
		self.index = len(self.history) - 1
		
	def gotoIndex(self, index):
		if index < 0 or index >= self.size(): return None
		self.index = index
		return self.history[self.index]
		
	def goBack(self, line=0):
		self.history[self.index].line = line
		self.index -= 1
		if self.index < 0: self.index = 0
		return self.history[self.index]
	
	def goForward(self, line=0):
		self.history[self.index].line = line
		self.index += 1
		if self.index >= self.size(): self.index = self.size() - 1
		return self.history[self.index]
		
	def canGoBack(self):
		return self.index > 0
	
	def canGoForward(self):
		return self.index < self.size() - 1
	
	def updateCurrent(self, url=None, title=None,line=None):
		if url: self.history[self.index].url = url
		if title: self.history[self.index].title = title
		if line: self.history[self.index].line = line
		
	def current(self):
		return self.history[self.index]
		
	def size(self):
		return len(self.history)
		
class WebWindow(xbmcgui.WindowXML):
	def __init__(self,*args,**kwargs):
		renderer = kwargs.get('renderer')
		self.buttons = renderer.buttons
		self.pageHeight = renderer.absoluteBottom()
		self.url = renderer.url
		self.forms = renderer.forms
		self.nextPage = ''
		self.nextURL = ''
		self.pageGroup = None
		self.started = False
		xbmcgui.WindowXML.__init__(self)
		
	def onInit(self):
		if self.started: return
		self.started = True
		self.pageGroup = self.getControl(100)
		self.window = xbmcgui.Window(xbmcgui.getCurrentWindowId())
		if WV.historyOffset: self.pageGroup.setPosition(0,WV.historyOffset)
				
	def movePage(self,x,y):
		x_pos,y_pos = self.pageGroup.getPosition()
		new_x = x_pos+x
		new_y = y_pos+y
		if new_x > 0:
			new_x = 0
		if new_y > 10:
			new_y = 10
		elif new_y + self.pageHeight < 710:
			new_y = 710 - self.pageHeight
		new_x = int(new_x)
		new_y = int(new_y)
		self.pageGroup.setPosition(new_x,new_y)
		self.reFocusLink(new_x,new_y)
		
	def reFocusLink(self,x,y):
		currentID = self.getFocusId()
		if currentID in self.buttons and self.buttonIsVisible(currentID, x, y): return
		keys = self.buttons.keys()
		keys.sort()
		for ID in keys:
			if self.buttonIsVisible(ID,x,y):
				self.setFocusId(ID)
				return
	
	def buttonIsVisible(self,ID,x,y):
		return self.buttons[ID]['y'] > abs(y) + 10 and self.buttons[ID]['y'] < abs(y) + 710
	
	def moveRight(self):
		self.movePage(-25, 0)
	
	def moveLeft(self):
		self.movePage(25, 0)
	
	def moveUp(self):
		self.movePage(0, 25)
	
	def moveDown(self):
		if self.pageHeight < 710: return
		self.movePage(0, -25)
	
	def pageUp(self):
		self.movePage(0, 700)
		
	def pageDown(self):
		if self.pageHeight < 710: return
		self.movePage(0, -700)
		
	def onAction(self, action):
# 		if action.getId() == ACTION_MOVE_RIGHT:
# 			self.moveRight()
# 		elif action.getId() == ACTION_MOVE_LEFT:
# 			self.moveLeft()
		if action.getId() == ACTION_MOVE_UP or action.getId() == 104:
			self.moveUp()
		elif action.getId() == ACTION_MOVE_DOWN  or action.getId() == 105:
			self.moveDown()
		elif action.getId() == ACTION_PAGE_UP or action.getId() == ACTION_PREV_ITEM:
			self.pageUp()
		elif action.getId() == ACTION_PAGE_DOWN or action.getId() == ACTION_NEXT_ITEM:
			self.pageDown()
		elif action.getId() == ACTION_CONTEXT_MENU:
			self.doMenu()
		elif action.getId() == ACTION_PARENT_DIR or action.getId() == ACTION_PARENT_DIR2:
			self.goBack()
		elif action.getId() == ACTION_PREVIOUS_MENU:
			WV.close()
		elif action.getId() == ACTION_PLAYER_PLAY:
			self.zoom()
		else:
			xbmcgui.WindowXML.onAction(self, action)
		
	def onClick(self,controlID):
		if controlID in self.buttons:
			data = self.buttons[controlID]
			#LOG('Button Data: %s' % data)
			dtype = data.get('type')
			if not dtype or dtype == 'LINK':
				if data['url'].lower().startswith('javascript:'):
					xbmcgui.Dialog().ok('Javascript','This is a javascipt link.','','WebViewer does not currently support javascript.')
					return
				url = urlparse.urljoin(self.url,data['url'])
				self.gotoNextPage(url)
			elif dtype == 'FORM:TEXT' or dtype == 'FORM:EMAIL':
				self.handleInput_TEXT(controlID, data)
			elif dtype == 'FORM:TEXTAREA':
				self.handleInput_TEXTAREA(controlID, data)
			elif dtype == 'FORM:PASSWORD':
				self.handleInput_TEXT(controlID, data, password=True)
			elif dtype == 'FORM:CHECKBOX':
				self.handleInput_CHECKBOX(controlID, data)
			elif dtype == 'FORM:RADIO':
				self.handleInput_RADIO(controlID, data)
			elif dtype == 'FORM:SELECT':
				self.handleInput_SELECT(controlID, data)
			elif dtype == 'FORM:SUBMIT':
				self.handleInput_SUBMIT(controlID, data)
			elif dtype == 'EMBED:VIDEO':
				if self.window.getProperty('current_video') == str(controlID) and video.isPlaying():
					xbmc.executebuiltin('Action(FullScreen)')
				else:
					video.stop()
					self.window.setProperty('current_video',str(controlID))
					video.play(data.get('url'),True)
			
	def zoom(self):
		zoom = self.window.getProperty('zoom_level')
		if zoom == 'ZOOM150':
			self.window.setProperty('zoom_level','ZOOM66')
		elif zoom == 'ZOOM66':
			self.window.setProperty('zoom_level','')
		else:
			self.window.setProperty('zoom_level','ZOOM150')
				
	def handleInput_TEXT(self,controlID,data,password=False):
		tag = data['tag']
		text = doKeyboard('Enter Text',tag.get('value',''),password)
		if text is None: return
		tag['value'] = text
		if password: text = '*' * len(text)
		self.getControl(controlID).setLabel(text)
		
	def handleInput_TEXTAREA(self,controlID,data):
		tag = data['tag']
		text = doKeyboard('Enter Text',tag.string or '')
		if text is None: return
		tag.string = text
		text = '[CR]'.join(textwrap.wrap(text, data['cols'] - 2)[:data['rows']])
		self.getControl(controlID).setLabel(text)
		
	def handleInput_CHECKBOX(self,controlID,data):
		tag = data['tag']
		checked = tag.get('checked') == '1'
		tag['checked'] = checked and '0' or '1'
		tex = checked and 'web-viewer-form-checkbox-unchecked.png' or 'web-viewer-form-checkbox-checked.png'
		self.getControl(controlID).setLabel(tex)
		
	def handleInput_RADIO(self,controlID,data):
		tag = data['tag']
		name = tag.get('name')
		form = self.forms[data.get('form')]
		for c in form:
			if hasattr(c,'name') and c.name == 'input' and c.get('name') == name:
				c['value'] = '0'
				ID = c.get('WV_ControlID')
				if ID: self.getControl(ID).setLabel('web-viewer-form-checkbox-unchecked.png')
		tag['value'] = '1'
		self.getControl(controlID).setLabel('web-viewer-form-checkbox-checked.png')

	def handleInput_SELECT(self,controlID,data):
		tag = data['tag']
		if tag.get('multiple') != None:
			while self.showSelectMenu(tag, controlID): pass
		else:
			self.showSelectMenu(tag, controlID)
		
	def showSelectMenu(self, tag, controlID):
		options = []
		display = []
		for opt in tag.contents:
			if hasattr(opt,'name') and opt.name == 'option':
				options.append(opt)
				if opt.get('disabled') != None:
					display.append('[COLOR FF808080]%s[/COLOR]' % opt.string)
				else:
					#display.append((opt.get('selected') != None and unichr(0x2611) or unichr(0x2610)) + ' ' + opt.string)
					display.append((opt.get('selected') != None and '[COLOR red]%s[/COLOR]' or '%s') % opt.string)
		dialog = xbmcgui.Dialog()
		idx = dialog.select('Options', display)
		if idx < 0: return False
		if tag.get('multiple') == None:
			for opt in options:
				if opt.get('selected') != None:
					del opt['selected']
		opt = options[idx]
		if opt.get('disabled') == None:
			if opt.get('selected') != None:
				del opt['selected']
			else:
				opt['selected'] = 'x'
		if tag.get('multiple') != None:
			ct = 0
			for opt in options:
				if  opt.get('selected') != None: ct += 1
			if ct:
				label = '%s Selected'.format(ct)
			else:
				label = None
		else:
			label = options[idx].string
		if label: self.getControl(controlID).setLabel(label)
		return True
	
	def handleInput_SUBMIT(self,controlID,data):
		form = self.forms[data.get('form')]
		WV.submitForm(data,form)
		
	def onFocus(self,controlID):
		if not self.pageGroup: return
	
		if controlID in self.buttons:
			button_y = int(self.buttons[controlID]['y'])
			button_h = int(self.buttons[controlID]['h'])
			x_pos,y_pos = self.pageGroup.getPosition()  # @UnusedVariable
			if button_y < abs(y_pos):
				self.pageGroup.setPosition(x_pos,10 - button_y)
			elif button_y + button_h > abs(y_pos) + 710:
				self.pageGroup.setPosition(x_pos,(0-button_y) + (710 - button_h))
		
	def doMenu(self):
		keyb = xbmc.Keyboard('','Enter URL')
		keyb.doModal()
		if not keyb.isConfirmed(): return
		url = keyb.getText()
		url = self.processURL(url)
		if not url: return
		self.gotoNextPage(url)
		
	def processURL(self,url):
		if not '://' in url: url = 'http://' + url
		return url
	
	def goBack(self):
		x_pos,y_pos = self.pageGroup.getPosition() # @UnusedVariable
		WV.goBack(y_pos)
		
	def gotoNextPage(self,url):
		x_pos,y_pos = self.pageGroup.getPosition() # @UnusedVariable
		WV.nextPage(url,y_pos)
			
class RenderElement:
	_font = ''
	_textColorDefault = ''
	def __init__(self,x,y,w,h):
		self.x = x
		self.y = y
		self.width = w
		self.height = h
		self.float = None
		
	def right(self):
		return self.x + self.width
	
	def adjustedRight(self):
		return self.right()
	
	def move(self,offset_x,offset_y):
		self.x += offset_x
		self.y += offset_y
		
class RenderContainer(RenderElement):
	_background = u'''		<control type="image">
				<posx>{x:.0f}</posx>
				<posy>{y:.0f}</posy>
				<width>{width:.0f}</width>
				<height>{height:.0f}</height>
				<texture{diffuse}>{texture}</texture>
				<colordiffuse>{colordiffuse}</colordiffuse>
				<aspectratio scalediffuse="false" align="{align}" aligny="{aligny}">{aspect}</aspectratio>
			</control>
'''
	_border = u'''		<control type="image">
				<posx>{x:.0f}</posx>
				<posy>{y:.0f}</posy>
				<width>{width:.0f}</width>
				<height>{height:.0f}</height>
				<texture border="5">{texture}</texture>
				<colordiffuse>{diffuse}</colordiffuse>
				<aspectratio>stretch</aspectratio>
			</control>
'''
	_borderTextures = (	'web-viewer-white-border-top.png',
						'web-viewer-white-border-right.png',
						'web-viewer-white-border-bottom.png',
						'web-viewer-white-border-left.png'	)
	
	def __init__(self,x=0,y=0,w=0,h=0,max_w=0,p=(0,0,0,0),m=(0,0,0,0),border_expand=0):
		RenderElement.__init__(self,x,y,w,h)
		self.padding = p
		self.padTop = p[0]
		self.padRight = p[1]
		self.padBottom = p[2]
		self.padLeft = p[3]
		self.marginTop = m[0]
		self.marginRight = m[1]
		self.marginBottom = m[2]
		self.marginLeft = m[3]
		
		self.borderExpand = border_expand
		self.tagName = ''
		self.block = True
		self.paddedLeft = self.x + self.padLeft + self.marginLeft
		self.contentWidth = self.width or max_w
		self.maxWidth = (self.width or max_w) + self.padLeft + self.padRight
		self.contentMaxXindex = 0
		self.setXIndex(self.paddedLeft)
		self.paddedTop = self.y + self.padTop + self.marginTop
		self.floatTop = self.paddedTop
		self.yindex = self.paddedTop
		self.xindex = self.paddedLeft
		self.background = None
		self.border = None
		self.maxYindex = self.paddedTop + self.height + self.padBottom + self.marginBottom
		self.floatCleared = False
		self.children = []
	
	def move(self,offset_x,offset_y):
		RenderElement.move(self, offset_x, offset_y)
		self.paddedLeft = self.x + self.padLeft + self.marginLeft
		self.paddedTop = self.y + self.padTop + self.marginTop
		self.floatTop += offset_y
		self.contentMaxXindex += offset_x
		self.yindex += offset_y
		self.xindex += offset_x
		self.maxYindex += offset_y
		for c in self.children: c.move(offset_x,offset_y)
		
	def updateMaxY(self,yindex=0):
		self.maxYindex = max(self.maxYindex, self.yindex, yindex)
		
	def setXIndex(self,x,add=False):
		if add:
			self.xindex += x
		else:
			self.xindex = x
		self.updateContentMaxX(self.xindex)
		
	def updateContentMaxX(self,xindex):
		self.contentMaxXindex = max(self.contentMaxXindex, self.xindex, xindex)
		
	def CR(self):
		self.setXIndex(self.paddedLeft)
		WV.renderer.lastImageBottom = 0
		return self
		
	def LF(self,absolute=False):
		if absolute:
			self.yindex = self.absoluteBottom()
		else:
			self.yindex = self.bottom()
		self.floatTop = self.yindex
		WV.renderer.lastImageBottom = 0
		return self
		
	def isCR(self):
		return self.xindex == self.paddedLeft
	
	def setBackground(self,bg):
		self.background = bg
		
	def setBorder(self,color):
		if color == True: color = WV.renderer.fgColor
		self.border = color
		
	def addChild(self,child):
		self.children.append(child)
		
	def clear(self):
		del self.children
		self.children = []
		
	def right(self):
		return self.x + self.marginLeft + self.usedWidth() + self.marginRight
	
	def contentRight(self):
		return (self.x + self.marginLeft + self.maxWidth) - self.padRight
	
	def paddedRight(self):
		return self.right() - self.padRight
	
	def usedWidth(self):
		if self.width: return max(self.width + self.padLeft + self.padRight,self.maxWidth)
		return (self.contentMaxXindex - (self.x + self.marginLeft)) + self.padRight
	
	def adjustedRight(self):
		right = self.paddedLeft
		for c in self.children:
			if c.float == 'right': continue
			right = max(right,c.adjustedRight())
		return right + self.padRight + self.marginRight
	
	def backgroundBottom(self):
		if self.height: return self.paddedTop + self.height + self.padBottom
		return self.bottom() + self.padBottom
	
	def bottom(self):
		bottom = self.yindex
		bottom = max(self.maxYindex,bottom)
		if self.hasBGImage():
			bottom2 = self.paddedTop + self.height
			bottom =  max(bottom,bottom2)
			
		if not self.floatCleared:
			for c in self.children:
				if not c.float: break
			else:
				return self.height + self.padBottom + self.marginBottom
		
		for c in self.children:
			if isinstance(c,RenderContainer):
				bottom = max(bottom,c.bottom()) #TODO: Should .bottom() be .containerBottom()? Behiving more correctly this way...
			else:
				bottom = max(bottom,c.y + c.height)
		return bottom
	
	def containerBottom(self):
		return self.bottom() + self.padBottom + self.marginBottom
	
	def absoluteBottom(self):
		bottom = max(self.maxYindex,self.yindex,self.y + self.padTop + self.height)
		for c in self.children:
			if isinstance(c,RenderContainer):
				bottom = max(bottom,c.absoluteBottom())
			else:
				bottom = max(bottom,c.y + c.height)
		return bottom

	def contentHeight(self):
		height = self.height
		if not self.floatCleared:
			for c in self.children:
				if not c.float: break
			else:
				return height
		
		for c in self.children:
			if isinstance(c,RenderContainer):
				if c.float and c.children: continue
				height = max(height,(c.bottom() - c.y) + self.padBottom)
			else:
				height = max(height,c.height + self.padBottom)
		return height
	
	def fullBottom(self):
		return self.bottom() + self.padBottom + self.marginBottom
	
	def hasBGImage(self):
		if not self.background: return False
		self.background.init()
		return self.background.image
	
	def xml(self):
		xml = ''
		if self.background:
			self.background.init()
			x = self.x + self.marginLeft
			y = self.y + self.marginTop
			if self.background.color:
				xml += self._background.format(	x=x,
												y=y,
												width=self.usedWidth(),
												height=self.backgroundBottom() - y,
												texture='web-viewer-white.png',
												aspect='stretch',
												aligny='center',
												align='center',
												diffuse='',
												colordiffuse=self.background.xbmcColor()	)
			if self.background.image and not self.background.image == 'none':
				aspect = 'center'
				aligny = 'center'
				alignx = 'center'
				mask = ''
				width = int(self.usedWidth())
				height = int(self.backgroundBottom() - y)
				w = h = 0
				absX = self.background.absPosX(width) or 0
				absY = self.background.absPosY(height) or 0
				if (absX and absX < 0) or (absY and absY < 0):
					alignx = 'left'
					aligny = 'top'
					if absX: x += absX
					if absY: y += absY
					if absX > 0: absX = 0
					if absY > 0: absY = 0
					fname = '%s-%s-%s-%s.png' % (width,height,absX,absY)
					fname = os.path.join(CACHE_PATH,fname)
					try:
						new_size = imageops.createOffsetMask(width, height, absX,absY, fname) or ''
					except:
						new_size = None
					if new_size:
						mask = ' diffuse="%s"' % fname
						width, height = new_size
				repeat = 1
				last = 0
				if self.background.repeat and self.background.repeat != 'no-repeat':
					if self.background.repeat == 'repeat':
						aspect = 'stretch'
					elif 'repeat' in self.background.repeat and self.background.repeat != 'no-repeat':
						info = style.getImageInfo(self.background.image, CACHE_PATH)
						if info: itype, w, h = info  # @UnusedVariable
					if self.background.repeat == 'repeat-x' or self.background.repeat == 'repeat-y':
						aspect = 'stretch'
						if self.background.repeat == 'repeat-x':
							if w > 1:
								aspect = 'center'
								alignx = 'left'
								height = min(h or height,height)
								repeat = int(width / w)
								last = width % w
								width = w
								if last: repeat += 1
							else:
								height = min(h or height,height)
								mask = ' border="0,0,1,0"' + mask
						else:
							if h == 1:
								if self.background.posX == 'right':
									x += (width - w)
								elif self.background.posX == 'center':
									x += int((width - w)/2.0)
								width = min(w or width,width)
								mask = ' border="0,0,0,1"' + mask
						
# 							width = min(w or width,width)
				
				if not mask:
					absX = self.background.absPosX(width)
					if absX is not None:
						x += absX
						alignx = 'left'
					else:
						alignx = self.background.posX
						
					absY = self.background.absPosY(height)
					if absY is not None:
						x += absY
						aligny = 'top'
					else:
						aligny = self.background.posY

				tex = self.background.image
				if tex.endswith('.gif'):
					cached = xbmcutil.getAndCacheImage(tex, CACHE_PATH)
					tex = xbmcutil.localCachePath(cached, CACHE_PATH)[:-4] + '.png'
					if not os.path.exists(tex): tex = imageops.gifToPng(cached,tex)
				for r in range(1,repeat + 1):
					if last and r == repeat: width = last
					xml += self._background.format(	x=x,
													y=y,
													width=width,
													height=height,
													texture=tex,
													aspect=aspect,
													aligny=aligny,
													align=alignx,
													diffuse=mask,
													colordiffuse='FFFFFFFF'	)
					x += w
				
		for c in self.children:
			xml += c.xml()
# 		if self.height == 31:
# 			if TEST:
# 				self.border = 'DDFF0000'
# 			else:
# 				self.border = 'DD0FF000'
# 			global TEST
# 			TEST = not TEST
		#self.border = '70000000'
		if self.border:
			x=self.x + self.marginLeft
			y=self.y + self.marginTop
			if isinstance(self.border,tuple):
				for b in range(0,4):
					if self.border[b]:
						xml += self._border.format(		x=x,
														y=y,
														width=self.usedWidth() + int(not(b % 1)),
														height=(self.backgroundBottom() - y) + (b % 1),
														texture=self._borderTextures[b],
														diffuse=self.border[b]	)
			else:
				xml += self._border.format(		x=x,
												y=y,
												width=self.usedWidth() + self.borderExpand,
												height=(self.backgroundBottom() - y) + self.borderExpand,
												texture='web-viewer-white-border.png',
												diffuse=self.border	)
# 				if self.marginLeft > 0: x = self.x
# 				if self.marginTop > 0: y = self.y
# 				xml += self._border.format(		x=x,
# 												y=y,
# 												width=self.usedWidth() + self.borderExpand + self.marginRight,
# 												height=(self.bottom() - self.y) + self.borderExpand,
# 												texture='web-viewer-white-border.png',
# 												diffuse='33FF0000'	)
		return xml
		
# TEST = False
	
class RenderTextbox(RenderElement):
	_xml = u'''		<control type="label">
				<posx>{x:.0f}</posx>
				<posy>{y:.0f}</posy>
				<width>{width:.0f}</width>
				<height>{height:.0f}</height>
				<font>{font}</font>
				<textcolor>{color}</textcolor>
				<label>{label}</label>
			</control>
'''
	
	def __init__(self,x=0,y=0,w=0,h=0):
		RenderElement.__init__(self,x,y,w,h)
		self.text = ''
		self.bold = ''
		self.textColor =  self._textColorDefault
		self._font = 'WebViewer-font12'
		
	def setFont(self,font):
		self._font = font
		
	def font(self):
		if self.bold: return 'Bold-' + self._font
		return self._font
	
	def setTextColor(self,color):
		self.textColor = color or self.textColor

	def color(self):
		return self.textColor
	
	def xml(self):
		return self._xml.format(	x=self.x,
									y=self.y,
									width=self.width+20,
									height=self.height+5,
									font=self.font(),
									color=self.color(),
									label=escapeXML(self.text)	)

class RenderImage(RenderElement):
	_xml = u'''		<control type="image">
				<posx>{x:.0f}</posx>
				<posy>{y:.0f}</posy>
				<width>{width:.0f}</width>
				<height>{height:.0f}</height>
				<texture fallback="web-viewer-broken-image.png"{textureborder}>{texture}</texture>
				{border}
				<colordiffuse>{diffuse}</colordiffuse>
				<aspectratio>{ratio}</aspectratio>
			</control>
'''
	_linkBorder = u'''<bordertexture border="2">web-viewer-link-border.png</bordertexture>
				<bordersize>1</bordersize>
'''

	def __init__(self,x=0,y=0,w=0,h=0):
		RenderElement.__init__(self,x,y,w,h)
		self.texture = ''
		self.border = 0
		self.link = False
		self.diffuse = 'FFFFFFFF'
		self.ratio = 'scaled'
		
	def borderAttribute(self):
		if not self.border: return ''
		return ' border="%s"' % self.border
	
	def xml(self):
		return self._xml.format(	x=self.x,
									y=self.y,
									width=self.width,
									height=self.height,
									texture=self.texture,
									textureborder=self.borderAttribute(),
									border=self.link and self._linkBorder or '',
									diffuse=self.diffuse,
									ratio=self.ratio	)
		
class RenderButton(RenderTextbox):
	_xml = u'''		<control type="button" id="{id}">
				<posx>{x:.0f}</posx>
				<posy>{y:.0f}</posy>
				<width>{width:.0f}</width>
				<height>{height:.0f}</height>
				<onleft>{onleft}</onleft>
				<onright>{onright}</onright>
				<texturefocus border="{texturefocusborder}">{texturefocus}</texturefocus>
				<texturenofocus>{texturenofocus}</texturenofocus>
				<align>{alignx}</align>
				<aligny>{aligny}</aligny>
				{textoffset}
				<textcolor>{color}</textcolor>
				<focusedcolor>FFFF0000</focusedcolor>
				<font>{font}</font>
				<label>{label}</label>
			</control>
'''
	_textOffset = u'''<textoffsetx>{textoffsetx}</textoffsetx>
				<textoffsety>{textoffsety}</textoffsety>
'''

	def __init__(self,x=0,y=0,w=0,h=0):
		RenderTextbox.__init__(self,x,y,w,h)
		self.id = 0
		self.onLeft = 0
		self.onRight = 0
		self.textureFocus = ''
		self.textureFocusBorder = 0
		self.textureNoFocus = '-'
		self.alignX = 'left'
		self.alignY = 'top'
		self.textOffsetX = 0
		self.textOffsetY = 0
		self.focusedColor = ''
		
	def textOffset(self):
		if self.textOffsetX or self.textOffsetY:
			return self._textOffset.format(textoffsetx=self.textOffsetX,textoffsety=self.textOffsetY)
		return ''
	
	def xml(self):
		return self._xml.format(	id=self.id,
									x=self.x,
									y=self.y,
									width=self.width,
									height=self.height,
									onleft=self.onLeft,
									onright = self.onRight,
									texturefocusborder=self.textureFocusBorder,
									texturefocus=self.textureFocus,
									texturenofocus=self.textureNoFocus,
									alignx=self.alignX,
									aligny=self.alignY,
									textoffset=self.textOffset(),
									font=self.font(),
									color=self.color(),
									label=escapeXML(self.text)	)

class RenderVideoWindow(RenderElement):
	_xml = u'''			<control type="image">
				<posx>{x:.0f}</posx>
				<posy>{y:.0f}</posy>
				<width>{width:.0f}</width>
				<height>{height:.0f}</height>
				<texture>web-viewer-play-overlay.png</texture>
				<aspectratio>scale</aspectratio>
				<visible>true</visible>
			</control>
			<control type="group">
				<posx>{x}</posx>
				<posy>{y}</posy>
				<control type="image">
					<posx>0</posx>
					<posy>0</posy>
					<width>{width}</width>
					<height>{height}</height>
					<texture>web-viewer-white.png</texture>
					<colordiffuse>FF000000</colordiffuse>
				</control>
				<control type="videowindow">
					<posx>0</posx>
					<posy>0</posy>
					<width>{width}</width>
					<height>{height}</height>
				</control>
				<visible>{visible}</visible>
			</control>
'''
	_visible = 'Player.Playing + Player.HasVideo + StringCompare(Window.Property(current_video),%s)'
	
	def __init__(self,x,y,w,h):
		RenderElement.__init__(self,x,y,w,h)
		self.linkedButton = 0
		
	def xml(self):
		return self._xml.format(	x=self.x,
									y=self.y,
									width=self.width,
									height=self.height,
									visible = self._visible % self.linkedButton	)

class WebPageRenderer(RenderContainer):
	fonts = {	'WebViewer-font20':{'w':14.0,'h':24.0,'xoff':0,'yoff':-2},
				'WebViewer-font18':{'w':11.0,'h':20.5,'xoff':0,'yoff':-2},
				'WebViewer-font16':{'w':9.5,'h':18.5,'xoff':0,'yoff':-2},
				'WebViewer-font14':{'w':8.5,'h':16.3,'xoff':0,'yoff':-2},
				'WebViewer-font12':{'w':7.4,'h':14.0,'xoff':0,'yoff':-1},
				'WebViewer-font10':{'w':6.4,'h':12.6,'xoff':0,'yoff':-1},
				'WebViewer-font8':{'w':5.4,'h':11.1,'xoff':0,'yoff':-1}
			}
	
	def __init__(self,url):
		self.reset(url)
		
	def reset(self,url):
		RenderContainer.__init__(self)
		self.clear()
		self.url = url
		self._xml = ''
		self.width = 1280
		self.maxWidth = 1280
		self.height = 700
		self.paddedLeft = 10
		self.contentWidth = self.width - (self.paddedLeft + self.paddedLeft)
		self.yindex = 0
		self.setXIndex(self.paddedLeft)
		self.floatLeftLines = 0
		self.floatLeftBottom = 0
		self.lastImageRight = 0
		self.lastImageLeft = 0
		self.floatRightLeft = 0
		self.floatRightBottom = 0
		self.lastImageBottom = 0
		self.leftIsEmpty = True
		self.forms = []
		self.formIDX = -1
		self.link = None
		self.center = False
		self.border = False
		self.textIndent = 0
		self.listStyle = None
		self.textMods = []
		self.fgColor = 'black'
		self.bgColor = 'ffffffff'
		self.linkColor = 'FF00AAAA'
		self.contentStarted = False
		self.buttonCt = 101
		self.encoding = 'UTF-8'
		self.encodingConfidence = 0
		self.buttons = {}
		self.textAttributes = {}
		self.setFont('WebViewer-font12')
		self.parser = 'None'
		RenderElement._textColorDefault = self.fgColor
		self.currentContainer = self

	def setCurrentContainer(self,container):
		state = self.currentContainer
		self.currentContainer = container
		return state
		
	def restoreCurrentContainer(self,state,inline=False,float_=None):
		state.setXIndex(self.currentContainer.xindex)
		if not inline and float_ != 'left' and float_ != 'right' and (self.currentContainer.contentHeight() or self.currentContainer.floatCleared):
			state.yindex = self.currentContainer.containerBottom()
		self.currentContainer = state
		
	
	def updateEncoding(self,detected):
		if not detected: return
		confidence = detected['confidence']
		if confidence < self.encodingConfidence: return
		self.encoding = detected['encoding']
		self.encodingConfidence = confidence
		
	def decode(self,text):
		text, detected = htmldecode.convertHTMLCodes(text, self.encoding)
		self.updateEncoding(detected)
		return text
	
	def formStart(self):
		self.formIDX += 1
		self.forms.append([])
	
	def formAddControl(self,control):
		if not self.forms: return #TODO: Handle controls not in a form
		self.forms[self.formIDX].append(control)
		
	def setURL(self,url):
		self.url = url
		
	def setFont(self,font):
		if not font in self.fonts: font = 'WebViewer-font12'
		self.font = font
		self.fontWidth = self.fonts[font]['w']
		self.fontHeight	= self.fonts[font]['h']
		self.fontXOff	= self.fonts[font]['xoff']
		self.fontYOff	= self.fonts[font]['yoff']
		
	def setColors(self,fg,bg):
		self.fgColor = fg.upper()
		self.bgColor = bg.lower()
		
	def resetSpaceLead(self,ct=None):
		if ct != None:
			self.floatLeftLines -= ct
			if self.floatLeftLines > 0: return
		else:
			self.lastImageRight = 0
			self.lastImageLeft = 0
		self.floatLeftBottom = 0
		self.floatLeftLines = 0
		
	def resetFloatRight(self):
		self.floatRightLeft = 0
		self.floatRightBottom = 0
		
	def writeWindow(self):
		with open(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('path')),'resources','skins','Default','720p','web-viewer-webpage-base.xml'),'r') as f:
			xml = f.read()
		xml = xml.replace('<!-- BGCOLOR -->',self.bgColor)
		xml = xml.replace('<!-- REPLACE -->',self.xml())
		with codecs.open(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('path')),'resources','skins','Default','720p','web-viewer-webpage.xml'),'w',encoding='UTF-8') as f:
			f.write(xml)
		return 'web-viewer-webpage.xml'
	
	def getNextButtonIDs(self,data,y,height):
		ID = self.buttonCt
		left = ID - 1
		right = ID + 1
		if left < 101: left = 101
		self.buttonCt += 1
		self.buttons[ID] = {'y':y,'h':height}
		self.buttons[ID].update(data)
		return ID,left,right
	
	def cssWorker(self,url,soup):
		try:
			css = urllib2.urlopen(url).read()
		except:
			ERROR('Worker failed to fetch css',hide_tb=True)
			return None
		try:
			view = style.getSoupView(soup, css, url)
		except:
			ERROR('Worker failed to process css')
			return None
		return view
	
	def processCSS(self,soup):
		start = time.time()
		urls = []
		styles = []
		if soup.head:
			for link in soup.head.findAll('link'):
				rel = link.get('rel',())
				if 'stylesheet' in rel and not 'alternate' in rel:
					url = urlparse.urljoin(self.url,link.get('href'))
					urls.append(([url,soup],None))
		for s in soup.findAll('style'):
			if s.string:
				styles.append(s.string)
				
		if not urls and not styles: return
		
		if urls:
			inc = 20.0/len(urls)
			WV.setProgressIncrement(inc)
			
			pool = threadpool.ThreadPool(4)
			requests = threadpool.makeRequests(self.cssWorker, urls)
			[pool.putRequest(req) for req in requests]
			results = pool.wait(return_results=True,progress=WV.updateProgressIncremental)
			pool.dismissWorkers()
			
			for view in results:
				if view: style.render2SoupStyle(view)
				
		for s in styles:
			view = style.getSoupView(soup, s, self.url)
			style.render2SoupStyle(view)
		duration = time.time() - start
		LOG('CSS Processed in %.2f seconds' % duration)
			
	def getImageInfos(self,soup):
		self.imageInfos = {}
		urls = []
		cached = 0
		ct = 0
		body = soup.body
		if not body: body = soup
		for img in body.findAll('img'):
			if img.get('src','').endswith('.gif'):
				url = urlparse.urljoin(self.url,img['src'])
				path = xbmcutil.getAndCacheImage(url, CACHE_PATH)
				dst = xbmcutil.localCachePath(path, CACHE_PATH)[:-4] + '.png'
				imageops.gifToPng(path, dst)
				
			ct+=1
			if not img.get('width') or not img.get('height'):
				styles = self.parseInlineStyle(img.get('style'))
				if styles:
					img['width'] = styles.get('width','').split(' ',1)[0]
					img['height'] = styles.get('height','').split(' ',1)[0]
			if not img.get('width') or not img.get('height'):
				url = urlparse.urljoin(self.url,img['src'])
				path = xbmcutil.getCachedImagePath(url,CACHE_PATH)
				if path:
					cached+=1
					with open(path,'r') as f:
						info = {'url':url}
						try:
							info['type'],info['w'],info['h'] = imageinfo.getImageInfo(f)
							self.imageInfos[url] = info
						except:
							continue	
				else:
					urls.append(url)
				
		LOG('%s images: Using %s images cached by XBMC; fetching info for %s images' % (ct,cached,len(urls)))
		if not urls: return
		inc = 40.0/len(urls)
		WV.setProgressIncrement(inc)
		self.imageInfos.update(imageinfo.getImageURLInfos(urls,threaded=True,progress=WV.updateProgressIncremental))
		
	def getWidthAndHeight(self,tag,ignore_pct=False,default=(None,None)):
		width = tag.get('width')
		height = tag.get('height')
		if not width or not height:
			styles = self.parseInlineStyle(tag.get('style'))
			if styles:
				if not width: width = styles.get('width','').split(' ',1)[0].replace('px','')
				if not height: height = styles.get('height','').split(' ',1)[0].replace('px','')
				
		if not width and not height: return default
		if ignore_pct: return width, height
		if width.endswith('%'): width = self.calculatePercentage(width[:-1], self.currentContainer.contentWidth)
		if height.endswith('%'): height = self.calculatePercentage(height[:-1], self.currentContainer.height)
		
		if default[0] == None:
			return width, height
		
		try:
			width = int(width)
		except:
			width = default[0]
		try:
			height = int(height)
		except:
			height = default[1]
		return width,height
		
		
	def calculatePercentage(self,pct,val):
		try:
			pct = int(pct)
		except:
			return pct
		if pct > 100: return val
		return int((pct/100.0) * val)
		
	def parseInlineStyle(self,styles=None,tag=None):
		if not styles:
			if tag: styles = tag.get('style')
			if not styles: return None
			
		styles = styles.split(';')
		ret = {}
		for style in styles:
			style = style.strip()
			if not style: continue
			try:
				k,v = style.split(':',1)
			except:
				continue
			ret[k.strip()] = v.strip()
		return ret
	
	def renderPage(self,html):
		self.ignore = ('script','style')
		try:
			soup = bs4.BeautifulSoup(html, "lxml")
			self.parser = 'LXML'
			LOG('Using: lxml')
		except:
			try:
				soup = bs4.BeautifulSoup(html, "html5lib")
				self.parser = 'HTML5LIB'
				LOG('Using: html5lib')
			except:
				soup = bs4.BeautifulSoup(html)
				self.parser = 'DEFAULT'
				LOG('Using: default')
		WV.updateProgress(20, 'Fetching/Processing Stylesheets')
		self.processCSS(soup)
		#codecs.open('/home/ruuk/test.html','w','UTF-8').write(soup.prettify())
		WV.updateProgress(40, 'Getting Image Info')	
		self.getImageInfos(soup)
		body = soup.body
		if not body: body = soup
		WV.updateProgress(80, 'Rendering Page')
		pct = 80
		blen = len(body.contents)
		if not blen: return
		bit = 20.0/blen
		bg = self.getTagBackground(body)
		if bg:
			bg.init()
			if bg.color: self.bgColor = bg.xbmcColor().lower()
		self.setBackground(bg)
		color = self.getFontColor(body)
		if color: self.fgColor = color
		for t in body.contents:
			self.processTag(t)
			pct+=bit
			WV.updateProgress(pct, 'Rendering Page')
		if self.floatLeftBottom > self.currentContainer.yindex: self.currentContainer.yindex = self.floatLeftBottom
			
	def addTextMod(self,mod):
		if not mod in self.textMods: self.textMods.append(mod)
		
	def delTextMod(self,mod):
		if mod in self.textMods: self.textMods.pop(self.textMods.index(mod))
		
	def textHasMod(self,mod):
		return mod in self.textMods
	
	def cleanWhitespace(self,text):
		base = text
		text = text.rstrip()
		if not text: return ''
		if text != base: text += ' '
		base = text
		text = text.lstrip()
		if text != base: text = ' ' + text
		return text

	def getFontColor(self,tag):
		styles = self.parseInlineStyle(tag=tag)
		if not styles or not 'color' in styles: return None
		color = styles.get('color')
		if '#' in color: return 'FF' + style.processColor(color.split('#',1)[-1][:6].upper())
		return None
	
	''' ----- Frequency ------
31.2818  #text      
 9.5278  br         
 9.1822  a          
 7.4688  td         
 6.2378  font       
 4.7963  tr         
 3.9655  img        
 3.8765  p          
 3.5474  span       
 3.2721  b          
 2.2265  ! or #comment 
 2.1986  center     
 1.7305  tbody      
 1.6318  table      
 1.5344  div        
 0.9987  option     
 0.9682  nobr       
 0.8739  li         
 0.8541  input      
 0.5880  i          
 0.3109  strong     
 0.2909  spacer     
 0.2580  hr         
 0.2282  noscript   
 0.2156  script     
 0.2067  small      
 0.1776  area       
 0.1602  form       
 0.1547  u          
 0.1535  ul         
 0.1340  dd         
 0.1056  body       
 0.0782  sub        
 0.0738  em         
 0.0671  big        
 0.0645  h2         
 0.0585  h1         
 0.0515  select     
 0.0512  h3         
 0.0486  th         
 0.0451  dt         
 0.0430  blockquote 
 0.0397  code       
 0.0337  pre        
 0.0301  h4         
 0.0277  map        
 0.0203  wbr        
 0.0090  style      
 0.0086  meta       
 0.0086  h5         
 0.0086  dl         
 0.0081  label      
 0.0080  size       
 0.0077  ol         
 0.0070  h6         
 0.0048  optgroup   
 0.0041  tt         
 0.0041  iframe     
 0.0034  noindex    
 0.0032  s          
 0.0028  textarea   
 0.0028  link       
 0.0018  base       
 0.0016  textbox    
 0.0016  noembed    
 0.0016  address    
 0.0015  caption    
 0.0012  dir        
 0.0011  strike     
 0.0008  cite       
 0.0008  acronym    
 0.0006  fieldset   
 0.0005  frame     
 0.0004  thead     
 0.0004  ilayer    
 0.0004  frameset  
 0.0004  col       
 0.0003  nolayer   
 0.0003  layer     
 0.0002  object   
 0.0002  menu     
 0.0001  nowrap    
 0.0001  embed     
 0.0001  dfn       
 0.0001  dev       
 0.0001  colgroup  
 0.0001  blink
 '''

	def processTag(self,tag):
		if isinstance(tag,bs4.Tag):
			if not self.tagIsVisible(tag): return
			if tag.name in self.ignore:	return
			self.checkTagGeneral(tag)
			if tag.name == 'br':			self.newLine()
			elif tag.name == 'a':			self.processA(tag)
			elif tag.name == 'img':			self.processIMG(tag)
			elif tag.name == 'p':			self.processP(tag)
			elif tag.name == 'span':		self.processSPAN(tag)
			elif tag.name == 'li': 			self.processLI(tag)
			elif tag.name == 'ul':			self.processUL(tag)
			elif tag.name == 'ol':			self.processUL(tag)
			elif tag.name == 'div':			self.processDIV(tag)
			elif tag.name == 'table':		self.processTABLE(tag)
			elif tag.name in ('td','th'):	self.processTD(tag)
			elif tag.name == 'dd':			self.processDD(tag)
			elif tag.name in ('tr','caption'): self.processTR(tag)
			elif tag.name == 'input':		self.processINPUT(tag)
			elif tag.name == 'textarea':	self.processTEXTAREA(tag)
			elif tag.name == 'select':		self.processSELECT(tag)
			elif tag.name == 'form':		self.processFORM(tag)
			elif tag.name in ('strong','b','em'):		self.processSTRONG(tag)
			elif tag.name == 'center':		self.processCENTER(tag)
			elif tag.name == 'iframe':		self.processIFRAME(tag)
			elif tag.name in ('blockquote','code'): self.processDIV(tag)
			elif tag.name in ('h1','h2','h3','h4','h5','h6'): self.processHX(tag)
			else:						self.processContents(tag)
		elif isinstance(tag,bs4.NavigableString):
			if not isinstance(tag,bs4.Comment):
				self.addText(self.cleanWhitespace(tag),button=self.link)
				return True
		return False
		
	def checkTagGeneral(self,tag):
		styles = tag.get('style','')
		if 'clear:' in styles:
			styles = self.parseInlineStyle(styles)
			clear = styles.get('clear')
			if clear == 'both':
				self.resetFloatRight()
				self.resetSpaceLead()
				self.currentContainer.floatCleared = True
			elif clear == 'right':
				self.resetFloatRight()
				self.currentContainer.floatCleared = True
			elif clear == 'left':
				self.resetSpaceLead()
				self.currentContainer.floatCleared = True
				
	def processFORM(self,tag):
		self.formStart()
		LOG('Form #%s' % self.formIDX)
		self.processContents(tag)
		
	def processTEXTAREA(self,tag):
		rows = tag.get('rows')
		cols = tag.get('cols')
		try:
			cols = int(cols)
		except:
			cols = 40
			
		try:
			rows = int(rows)
		except:
			rows = 10
			
		width,height = self.getWidthAndHeight(tag,default=(int(cols * self.fontWidth),int(rows * self.fontHeight))) # @UnusedVariable
		
		cols = int(width/self.fontWidth)
		wrapwidth = cols - 2
		val = '[CR]'.join(textwrap.wrap(tag.string or '', wrapwidth)[:rows])
		self.addImage(tag, width, height,ratio='stretch', button={'type':'FORM:TEXTAREA','form':self.formIDX,'tag':tag,'cols':cols,'rows':rows},texture='web-viewer-form-text.png',textureborder=5,text=val,textcolor='black',alignx='left',aligny='top')
		self.formAddControl(tag)
			
	def processSELECT(self,tag):
		val = 'Choose...'
		for t in tag.contents:
			if hasattr(t,'name') and t.name == 'option':
				val = t.string
				break
		width = int(self.fontWidth * (len(val)+2))
		self.addImage(tag, width, self.fontHeight,ratio='stretch', button={'type':'FORM:SELECT','form':self.formIDX,'tag':tag},texture='web-viewer-form-submit.png',textureborder=5,text=val,textcolor='black',alignx='center',aligny='center')
		self.formAddControl(tag)

	def processINPUT(self,tag):
		ttype= tag.get('type','text')
		height = self.fontHeight
		margin = self.getTagMargin(tag)
		pad = self.getTagPadding(tag)
		if ttype == 'text' or ttype == 'password' or ttype == 'email':
			w, h = self.getWidthAndHeight(tag)  # @UnusedVariable
			try:
				width = int(w)
			except:
				width = 0
			if not width:
				size = tag.get('size')
				try:
					width = int(self.fontWidth * int(size))
				except:
					width = int(20 * self.fontWidth)
			try:
				height = int(h)
			except:
				height = self.fontHeight
				
			height = max(height, self.fontHeight) + pad[0] + pad[2]
			width = width + pad[3] + pad[1]
			val = tag.get('value') or ''
			src = 'web-viewer-form-text.png'
			bg = self.getTagBackground(tag)
			if bg and ('none' in bg.background or 'transparent' in bg.background): src = '-'
			self.addImage(tag, width, height,ratio='stretch', button={'type':'FORM:%s' % ttype.upper(),'form':self.formIDX,'tag':tag},texture=src,textureborder=5,text=val,textcolor='black',alignx='left',aligny='center',margin=margin)
		elif ttype == 'checkbox' or ttype == 'radio':
			checked = tag.get('checked') == '1'
			tex = checked and 'web-viewer-form-checkbox-checked.png' or 'web-viewer-form-checkbox-unchecked.png'
			ID = self.addImage(tag, self.fontWidth, self.fontHeight,ratio='keep', button={'type':'FORM:%s' % ttype.upper(),'form':self.formIDX,'tag':tag},text=tex,texture='$INFO[Control.GetLabel({id})]')
			tag['WV_ControlID'] = ID
		elif ttype == 'submit' or ttype == 'image':
			if ttype == 'image':
				src = urlparse.urljoin(self.url,tag.get('src',''))
				val = ''
				width, height = self.getWidthAndHeight(tag)
				if width is None:
					try:
						itype, width, height = imageinfo.getImageURLInfo(src)  # @UnusedVariable
					except:
						pass
				try:
					width = int(width)
					height = int(height)
				except:
					width = int(self.fontWidth * 6)
					height = self.fontHeight
			else:
				w, h = self.getWidthAndHeight(tag)  # @UnusedVariable
				val = tag.get('value') or ''
				try:
					width = int(w)
				except:
					width = int(self.fontWidth * (len(val)+2))
				try:
					height = max(int(h),self.fontHeight)
				except:
					height = self.fontHeight
				src = 'web-viewer-form-submit.png'
				bg = self.getTagBackground(tag)
				if bg and ('none' in bg.background or 'transparent' in bg.background): src = '-'
			self.addImage(tag, width, height,ratio='stretch', button={'type':'FORM:SUBMIT','form':self.formIDX,'tag':tag},texture=src,textureborder=5,text=val,textcolor='black',alignx='center',aligny='center')
		else:
			self.processContents(tag)
		self.formAddControl(tag)
			
	def processA(self,tag):
		inline = self.tagIsInline(tag, True)
		if not inline or 'background' in tag.get('style','') or not tag.string:
			link = tag.get('href')
			if link: self.link = {'url':link}
			self.processContainerElement(tag, inline)
			self.link = None
		else:
			if tag.string:
				pad = self.getTagPadding(tag)
				padl = ''
				padr = ''
				if pad[3]: padl = ' ' * (int(pad[3] / self.fontWidth) or 1)
				if pad[1]: padr = ' ' * (int(pad[1] / self.fontWidth) or 1)
				self.addText(tag.string + padr,color=self.linkColor,button={'url':tag.get('href')},pre=padl)
	# 			x = self.currentContainer.xindex
	# 			y = self.currentContainer.yindex
	# 			tb = self.addText(tag.string,color=self.linkColor,button={'url':tag.get('href')})
	# 			if not '[CR]' in tb.text:
	# 				w = len(tb.text.strip()) * self.fontWidth
	# 				h = self.fontHeight
	# 				a = RenderContainer(x,y,w,h,w,p=self.getTagPadding(tag))
	# 				a.updateMaxY(y + self.fontHeight)
	# 				a.setBackground(self.getTagBackground(tag))
	# 				a.setBorder(self.getTagBorder(tag))
	# 				self.currentContainer.children.insert(-1,a)
			else:
				self.processContents(tag,link=tag.get('href'))
			
	def processDIV(self,tag):
		if tag.get('itemtype') and '/VideoObject' in tag['itemtype']:
			url = ''
			thumbnail = ''
			width = ''
			height = ''
			for t in tag.contents:
				if hasattr(t,'name') and t.name in ('link','meta'):
					prop = t.get('itemprop','')
					if not prop: continue
					if prop == 'url':
						if not url: url = t.get('href')
					elif prop == 'thumbnailUrl':
						thumbnail = t.get('href','')
					elif prop == 'width':
						width = t.get('content',640)
					elif prop == 'height':
						height = t.get('content',480)
					elif prop == 'embedURL':
						url = t.get('href','')
			obj = None
			if url and WV.video.mightBeVideo(url): obj = WV.video.getVideoObject(url)
			if obj:
				try:
					width = int(width)
					height = int(height)
					if width > 640:
						height = int((640.0/width) * height)
						width = 640
				except:
					width = 640
					height = 480
				self.addImage(tag, width, height, button={'url':obj.getPlayableURL(),'type':'EMBED:VIDEO'}, ratio='stretch', texture=thumbnail or obj.thumbnail)

			else:
				self.newLine()
				self.processContents(tag)
				self.newLine()			
		else:
			return self.processContainerElement(tag)
			
	def processContainerElement(self,tag,inline=False,pre=None,pre_LF=True,post_LF=True):
		#if not tag.contents: return
		inline = self.tagIsInline(tag,inline)
		float_ = self.getTagFloat(tag)
		#if not float_ and self.currentContainer.float and self.currentContainer.float != 'parent': float_ = 'parent' #TODO: Handle clearing of the float properly as this likely isn't it
		if not inline and self.currentContainer.children:
			if not float_: self.currentContainer.CR()
			if pre_LF and float_ != 'left' and float_ != 'right':
				if not self.currentContainer.children:
					pass
					#self.currentContainer.LF()
				else:
					lastChild = self.currentContainer.children[-1]
					if isinstance(lastChild,RenderTextbox):
						self.currentContainer.yindex = max(self.currentContainer.yindex, lastChild.y + lastChild.height)
			#if not isinstance(self.currentContainer.children[-1],RenderContainer): self.currentContainer.LF()
		padding = self.getTagPadding(tag)
		margin = self.getTagMargin(tag)
		w,h = self.getWidthAndHeight(tag)  # @UnusedVariable
		maxw = self.currentContainer.contentWidth - (margin[3] + padding[3] + padding[1] + margin[1])
		try:
			h = int(h)
		except:
			h = 0
		try:
			w = int(w)
		except:
			if (inline and inline != 'inline-block') or float_:
				w = 0
			else:
				w = maxw
		x = self.currentContainer.xindex
		y = self.currentContainer.yindex
		pos = self.getTagPosition(tag)
		if pos:
			if pos.get('position') == 'absolute':
				try:
					left = int(re.search('\d+',pos.get('left','')).group(0))
					x = self.currentContainer.x + left
				except:
					ERROR('Error Parsing Postion: ({0})'.format(pos.get('left')),hide_tb=True)
					
				try:
					top = int(re.search('\d+',pos.get('top','')).group(0))
					y = self.currentContainer.y + top
				except:
					ERROR('Error Parsing Postion: ({0})'.format(pos.get('top')),hide_tb=True)
					
			elif pos.get('position') == 'relative':
				if pos.get('bottom'):
					try:
						y -= int(re.search('\d+',pos.get('bottom','')).group(0))
					except:
						ERROR('Error Parsing Postion: ({0})'.format(pos.get('bottom')),hide_tb=True)
						
		style = tag.get('style','')
		if w and 'margin: 0 auto' in style: #TODO: Obviously, this is a dumb way to parse out a centering margin :)
			x = self.currentContainer.x + int((self.currentContainer.contentWidth - w) / 2)
			if x < self.currentContainer.x: x = self.currentContainer.x
		elif float_ == 'right':
			if w:
				x = self.currentContainer.paddedRight() - w
				#if x >= self.currentContainer.contentMaxXindex:
				#	y = self.currentContainer.floatTop
			else:
				x = self.currentContainer.adjustedRight()
				#y = self.currentContainer.floatTop
				#print self.currentContainer.adjustedRight()
				#if x >= self.currentContainer.contentMaxXindex:
				#	y = self.currentContainer.y
					
		elif float_ == 'left' and not (pos and pos.get('position') == 'fixed'):
			x = max(x,self.currentContainer.paddedLeft)
			if self.currentContainer.children:
				prev = self.currentContainer.children[-1]
				if prev.float == 'left':
					x = prev.adjustedRight()
			#x = max(x,self.currentContainer.adjustedRight())
# 			if w:
# 				if x + w <= self.currentContainer.paddedRight():
# 					y = self.currentContainer.floatTop
# 			else:
# 				if x <= self.currentContainer.paddedRight():
# 					y = self.currentContainer.floatTop
		self.currentContainer.updateMaxY()
		div = RenderContainer(x,y,w,h,maxw,padding,margin)
		div.tagName = 'div'
		div.block = not inline
		div.float = float_
		self.currentContainer.addChild(div)
		state = self.setCurrentContainer(div)
		div.setBackground(self.getTagBackground(tag))
		div.setBorder(self.getTagBorder(tag))
		lastCenter = self.center
		if 'center;' in tag.get('style',''): self.center = True
		if pre: self.addText(pre)
		text_state = self.setTextAttributes(tag)
		self.processContents(tag)
		self.restoreTextAttributes(text_state)
		self.center = lastCenter
# 		if not inline:
# 			if div.children and not isinstance(div.children[-1],RenderContainer):
# 				if post_LF and float_ != 'right' and float_ != 'left': self.currentContainer.LF()
		if float_ == 'right':
			offset = state.contentRight() - div.adjustedRight()
			if offset > 0:
				if offset: div.move(offset,0)
			self.setFloatRight(div, div.x - div.marginRight, div.containerBottom())
		elif div.adjustedRight() > state.contentRight():
			xoff = state.paddedLeft - div.x
			yoff = state.bottom() - div.y
			div.move(xoff,yoff)
# 		elif float_ == 'left':
# 			self.setFloatLeft(state,div.usedWidth(), div.height)
		#if tag.name == 'ul':
		#	print (tag.get('id'),div.contentHeight())
		self.restoreCurrentContainer(state,inline,float_)
		self.currentContainer.updateContentMaxX(div.right())
		if not inline:
			if not float_: self.currentContainer.CR()
		else:
			self.currentContainer.setXIndex(div.right())
		
	def setTextAttributes(self,tag):
		state = self.textAttributes.copy()
		styles = self.parseInlineStyle(tag=tag)
		if not styles: return state
		if 'line-height' in styles:
			lh = styles['line-height']
			try:
				h = int(re.search('\d+',lh).group(0))
				if '%' in lh: h = int((h/100.0) * self.fontHeight)
				offset = int((h - self.fontHeight) / 2)
				if offset > 0:
					self.textAttributes['heightOffset'] = offset
			except:
				pass
		return state
	
	def restoreTextAttributes(self,state):
		self.textAttributes = state
		
	def processIMG(self,tag):
		margin = self.getTagMargin(tag)
		style = tag.get('style','')
		#TODO: Remove when we handle float: right
		if 'float: right' in style:
			margin = (margin[0],margin[3],margin[2],margin[1])
		self.addImage(tag,button=self.link,margin=margin)
		#Remove          ^    ^
		
	def processTABLE(self,tag):
		self.currentContainer.CR()
		table = RenderContainer(self.currentContainer.xindex,self.currentContainer.yindex,self.currentContainer.contentWidth,self.currentContainer.height,self.currentContainer.contentWidth)
		self.currentContainer.addChild(table)
		state = self.setCurrentContainer(table)
		self.border = self.getTagBorder(tag)
		table.setBorder(self.border)
		self.processContents(tag)
		self.currentContainer.yindex += 1
		self.restoreCurrentContainer(state)
		self.currentContainer.updateContentMaxX(table.right())
		self.border = False
		self.newLine()
		
	def processTR(self,tag):
		self.currentContainer.CR()
		padding = (0,0,0,0)
		if tag.name == 'caption': padding = self.getTagPadding(tag,4)
		row = RenderContainer(self.currentContainer.xindex,self.currentContainer.yindex,self.currentContainer.contentWidth - (padding[3] + padding[1]),self.currentContainer.height,self.currentContainer.contentWidth,padding)
		self.currentContainer.addChild(row)
		state = self.setCurrentContainer(row)
		if tag.name == 'caption': self.addTextMod('bold')
		
		tds = []
		left_tds = []
		twidth = self.currentContainer.contentWidth
		left = twidth
		
		for td in tag.contents:
			if not hasattr(td,'name'): continue
			if not td.name in ('td','th'): continue
			
			w, h = self.getWidthAndHeight(td,ignore_pct=True)  # @UnusedVariable
			try:
				if w.endswith('%'):
					w = int(w.strip(' %'))
					w = self.calculatePercentage(w, twidth)
				w = int(w)
			except:
				w=0
			left -= w
			if w:
				td['width'] = w
			else:
				left_tds.append(td)
			tds.append(td)
		if left_tds:
			w = int(left/len(left_tds))
			for td in left_tds: td['width'] = w
		x = row.xindex
		y = row.y
		
		for td in tds:
			w = td['width']
			td['table_pos'] = (x,y,w)
			x+=w		
				
		self.processContents(tag)
		self.currentContainer.LF()
		self.currentContainer.updateMaxY()
		rbottom = row.bottom()
		for tdc in row.children:
			if isinstance(tdc,RenderContainer):
				tdc.updateMaxY(rbottom)
		self.delTextMod('bold')
		row.setBackground(self.getTagBackground(tag))
		row.setBorder(self.getTagBorder(tag))
		
		self.restoreCurrentContainer(state)
		self.currentContainer.CR()
		
	def processTD(self,tag):
		x,y,w = tag.get('table_pos',(self.currentContainer.xindex,self.currentContainer.y,tag.get('width',200)))
		if str(w).endswith('%'): w = self.calculatePercentage(str(w)[:-1], self.currentContainer.contentWidth)
		padding = self.getTagPadding(tag,2)
		w = w - (padding[3] + padding[1])
		td = RenderContainer(x,y,w,self.currentContainer.height,w,padding,border_expand=1)
		self.currentContainer.addChild(td)
		state = self.setCurrentContainer(td)
		td.setBackground(self.getTagBackground(tag))
		td.setBorder(self.getTagBorder(tag) or self.border)
		if tag.string:
			self.addText(tag.string)
		else:
			lastCenter = self.center
			if 'center;' in tag.get('style',''): self.center = True
			self.processContents(tag)
			#self.addText(' ')
			self.center = lastCenter
		#if td.children and isinstance(td.children[-1],RenderTextbox): self.newLine()
		state.updateMaxY(td.bottom())
		self.restoreCurrentContainer(state)
		
	def processDD(self,tag):
		if tag.string:
			self.addText(tag.string + ' ')
		else:
			self.processContents(tag)
			self.addText(' ')
			
	def processSTRONG(self,tag):
		self.addTextMod('bold')
		self.processContents(tag)
		self.delTextMod('bold')
			
	def processCENTER(self,tag):
		lastCenter = self.center
		self.center = True
		self.processContents(tag)
		self.center = lastCenter
			
	def processIFRAME(self,tag):
		src = tag.get('src')
		if WV.video.mightBeVideo(src):
			obj = WV.video.getVideoObject(src)
			if obj and obj.isVideo and obj.thumbnail:
				try:
					width = int(tag.get('width',640))
					height = int(tag.get('height',480))
				except:
					width = 640
					height = 480 
				self.addImage(tag, width, height, button={'url':obj.getPlayableURL(),'type':'EMBED:VIDEO'}, ratio='stretch', texture=obj.thumbnail)
			else:
				self.addText(obj.title or 'IFRAME',color=self.linkColor,button={'url':tag.get('href')})
		else:
			self.addText('IFRAME',color=self.linkColor,button={'url':tag.get('href')})
		
		
	def processSPAN(self,tag):
		inline = self.tagIsInline(tag, True)
		if not inline:
			self.processContainerElement(tag, inline)
		else:	
			self.processContents(tag)
			self.addText(' ')
		
	def processP(self,tag):
		if not self.floatRightBottom and not self.floatLeftLines:
			self.currentContainer.CR().LF(absolute=True)
		self.processContainerElement(tag)
# 		self.newLine()
# 		self.processContents(tag)
# 		self.newLine()
		
	def processUL(self,tag):
		#self.newLine()
		lsState = self.listStyle
		ls = (self.parseInlineStyle(tag=tag) or {}).get('list-style','')
		if ls: self.listStyle = ls
		self.processContainerElement(tag)
		self.listStyle = lsState
		#self.processContents(tag)
		#self.newLine()
		
	def processLI(self,tag):
		inline = self.tagIsInline(tag)
		#if not inline: self.newLine()
		styles = tag.get('style','')
		pre = None
		if self.listStyle != 'none' and (not 'list-style' in styles or not 'none' in self.parseInlineStyle(tag=tag).get('list-style','')):
			pre = u'%s ' % unichr(8226)
		self.processContainerElement(tag, inline,pre=pre,pre_LF=False,post_LF=False)
		#self.processContents(tag)
		
	def processHX(self,tag):
		self.newLine()
		self.addTextMod('bold')
		if tag.name == 'h1':
			self.setFont('WebViewer-font20')
		elif tag.name == 'h2':
			self.setFont('WebViewer-font16')
		elif tag.name == 'h3':
			self.setFont('WebViewer-font14')
		elif tag.name == 'h5':
			self.setFont('WebViewer-font10')
		elif tag.name == 'h6':
			self.setFont('WebViewer-font8')
		else:
			self.setFont('WebViewer-font12')
		self.processContainerElement(tag)
		self.setFont('WebViewer-font12')
		self.delTextMod('bold')
	
	def setFontColor(self,tag):
		styles = self.parseInlineStyle(tag=tag)
		if not styles or not 'color' in styles: return self.fgColor
		state = RenderElement._textColorDefault
		if '#' in styles['color']: RenderElement._textColorDefault = 'FF' + style.processColor(styles['color'].split('#',1)[-1][:6].upper())
		return state
		
	def restoreFontColor(self,state):
		RenderElement._textColorDefault = state
		
	def tagIsVisible(self,tag):
		styles = tag.get('style','')
		if not 'visibility' in styles and not 'display' in styles: return True
		styles = self.parseInlineStyle(styles)
		if 'hidden' in styles.get('visibility',''): return False
		if 'none' in styles.get('display',''): return False
		return True
	
	def getTagPosition(self,tag):
		styles = self.parseInlineStyle(tag=tag)
		if not styles: return None
		ret = {}
		if 'position' in styles: ret['position'] = styles.get('position')
		if 'top' in styles: ret['top'] = styles.get('top')
		if 'left' in styles: ret['left'] = styles.get('left')
		if 'bottom' in styles: ret['bottom'] = styles.get('bottom')
		if 'right' in styles: ret['right'] = styles.get('right')
		return ret
		
	def getTagPadding(self,tag,default=0):return self.getTagSpacing('padding', tag, default)
	
	def getTagMargin(self,tag,default=0): return self.getTagSpacing('margin', tag, default)
		
	def getTagSpacing(self,prefix,tag,default):
		styles = self.parseInlineStyle(tag=tag)
		spacing = [default] * 4
		if not styles: return tuple(spacing)
		if prefix in styles:
			p = styles[prefix].split(' ')
			#p = self.intList(re.findall('-?\d+',styles[prefix]),default)
			if not p: return (default,) * 4
			plen = len(p)
			if plen == 1:
				tb = self.processSpacing(p[0], True)
				lr = self.processSpacing(p[0])
				spacing = [tb,lr,tb,lr]
			elif plen == 2:
				tb = self.processSpacing(p[0], True)
				lr = self.processSpacing(p[1])
				spacing = [tb,lr,tb,lr]
			elif plen == 3:
				t = self.processSpacing(p[0], True)
				b = self.processSpacing(p[2], True)
				lr = self.processSpacing(p[1])
				spacing =  [t,lr,b,lr]
			else:
				t = self.processSpacing(p[0], True)
				r = self.processSpacing(p[1])
				b = self.processSpacing(p[2], True)
				l = self.processSpacing(p[3])
				spacing = [t,r,b,l]
		if prefix + '-top' in styles: spacing[0] =  self.processSpacing(styles[prefix + '-top'],True)
		if prefix + '-right' in styles: spacing[1] =   self.processSpacing(styles[prefix + '-right'])
		if prefix + '-bottom' in styles: spacing[2] =  self.processSpacing(styles[prefix + '-bottom'],True)
		if prefix + '-left' in styles: spacing[3] =  self.processSpacing(styles[prefix + '-left'])
		return tuple(spacing)
	
	def processSpacing(self,val,is_height=False):
		if val == 'auto': return False
		try:
			if val.endswith('px'): return float(val[:-2])
			if val.endswith('em'):
				if is_height:
					return float(val[:-2]) * self.fontHeight
				else:
					return float(val[:-2]) * self.fontWidth
		except:
			return False
		return 0
	
	def getTagFloat(self,tag): #TODO: Do this properly
		style = tag.get('style')
		if not style: return False
		if 'float: right' in style:
			return 'right'
		elif 'float: left' in style:
			return 'left'
		return False
			
	def getDirectionalSpacing(self,val,default):
		try:
			return int(re.search('-?\d+',val).group(0))
		except:
			return default
		
	def intList(self,slist,default):
		ret = []
		for s in slist:
			try: i = int(s)
			except: i = default
			ret.append(i)
		return ret
	
	def getTagBackground(self,tag):
		styles = tag.get('style','')
		if not 'background' in styles: return None
		styles = self.parseInlineStyle(styles,tag=tag)
		if not styles: return None
		return style.CSSBackground(styles,CACHE_PATH)
	
	def getTagBorder(self,tag):
		if tag.get('border','0') != '0': return True
		styles = tag.get('style','')
		if not 'border' in styles: return False
		styles = self.parseInlineStyle(styles,tag=tag)
		if not styles: return False
		if 'border' in styles:
			return self.extractBorderColor(styles)
		top = right = bottom = left = False
		if 'border-top' in styles:
			top = self.extractBorderColor(styles, '-top')
		elif 'border-right' in styles:
			right = self.extractBorderColor(styles, '-right')
		elif 'border-bottom' in styles:
			bottom = self.extractBorderColor(styles, '-bottom')
		elif 'border-left' in styles:
			left = self.extractBorderColor(styles, '-left')
		if top or right or bottom or left:
			return (top,right,bottom,left)
		return False
		
	def extractBorderColor(self,styles,prefix=''):
		val = styles['border' + prefix]
		if '#' in val: return 'FF' + style.processColor(val.split('#',1)[-1][:6].upper())
	
	def tagIsInline(self,tag,default=False): #TODO: Handle this properly
		styles = self.parseInlineStyle(tag=tag)
		if not styles: return default
		if not 'display' in styles: return default
		if 'inline' in styles['display']:
			return styles['display']
		elif 'block' in styles['display']:
			return False
		return default
		
	def newLine(self,lines=1):
		if not self.contentStarted: return
		self.leftIsEmpty = True
		if self.floatLeftBottom and self.floatLeftBottom > self.currentContainer.yindex:
			self.currentContainer.yindex = self.floatLeftBottom
			lines -=1
		if self.currentContainer.yindex > self.floatRightBottom: self.resetFloatRight()
		self.floatLeftBottom = 0
		self.currentContainer.yindex += self.fontHeight * lines
		self.currentContainer.floatTop = self.currentContainer.yindex
		self.currentContainer.CR()
		self.leftIsEmpty = True
		self.resetSpaceLead()
		self.lastImageBottom = 0
		
	def processContents(self,tag,link=None):
		if link: self.link = {'url':link}
		hasText = False
		indent = 0
		fgstate = self.setFontColor(tag)
		if 'text-indent' in tag.get('style',''):
			try:
				indent = float(self.parseInlineStyle(tag=tag).get('text-indent').replace('px','').replace('em',''))
			except:
				ERROR('Bad text-indent',hide_tb=True)
		if indent:
			current = self.textIndent
			if indent < -100: indent *= 2
			self.textIndent = indent
		for t in tag.contents:
			if self.processTag(t): hasText = True
		if link: self.link = None
		if indent: self.textIndent = current
		self.restoreFontColor(fgstate)
		return hasText
		
	def firstWordTooLong(self,text,wrapwidth,lead):
		firstLen = len(textwrap.TextWrapper.wordsep_re.split(text.lstrip(),1)[0])  # @UndefinedVariable
		#print '%s %s %s %s' % (firstLen,wrapwidth,lead,repr(text[:8]))
		return firstLen > (wrapwidth - lead)
	
	def wrap(self,text,pre=''):
		if self.currentContainer.yindex >= self.floatRightBottom: self.resetFloatRight()
		if self.currentContainer.yindex < self.floatRightBottom:
			return self.wrapFloatRight(text, pre)
		if self.currentContainer.yindex >= self.floatLeftBottom: self.resetSpaceLead()
		
		si = ''
		silen = 0
		sllen = int(math.ceil((self.currentContainer.xindex - self.currentContainer.paddedLeft) / self.fontWidth))
		wrapwidth = int((self.currentContainer.contentWidth - self.textIndent)/self.fontWidth)
		if wrapwidth < 1: wrapwidth = 1
		if self.lastImageRight:
			silen = int(math.ceil((self.lastImageRight - self.currentContainer.paddedLeft) / self.fontWidth))
			si = ' ' * silen
			
		if self.firstWordTooLong(text, wrapwidth, sllen):
			if self.floatLeftBottom:
				self.currentContainer.yindex = self.floatLeftBottom
				self.floatLeftBottom = 0
				self.currentContainer.CR()
				self.resetSpaceLead()
			else:
				self.newLine(self.floatLeftLines or 1)
			sllen = int(math.ceil((self.currentContainer.xindex - self.currentContainer.paddedLeft) / self.fontWidth))
		
		spaceLead = ' ' * sllen
		if not sllen: text = pre + text.lstrip()
		if silen >= wrapwidth:
			lines = ['ERROR']
			LOG('Error wrapping text: [{0}]'.format(repr(text[:50])))
		else:
			lines = textwrap.wrap(spaceLead + text, wrapwidth,drop_whitespace=False,subsequent_indent=si)
		end = []
		start = lines
		if not self.lastImageRight and self.floatLeftLines > 1 and len(lines) > 1:
			lines = lines[:1] + ([''] * (self.floatLeftLines - 1)) + lines[1:]
			self.resetSpaceLead()
		else:
			if sllen and self.floatLeftLines and self.floatLeftLines < len(lines):
				start = lines[0:self.floatLeftLines]
				end = textwrap.wrap(''.join(lines[self.floatLeftLines:]),wrapwidth)
				self.resetSpaceLead()
				lines = start + end
		if len(start) > 1:
			for i in range(1,len(start)):
				self.floatLeftLines -= 1
				if self.floatLeftLines < 0:
					self.resetSpaceLead()
				start[i] = si + start[i].lstrip()

		#if sllen and len(lines) > 1 and not lines[0].strip(): lines.pop(0)
		return start + end
		
	def wrapFloatRight(self,text,pre=''):
		floatRightLines = int(math.ceil((self.floatRightBottom - self.currentContainer.yindex) / float(self.fontHeight)))
		sllen = int(math.ceil((self.currentContainer.xindex - self.currentContainer.paddedLeft) / self.fontWidth))
		spaceLead = ' ' * sllen
		wrapwidth = int(((self.floatRightLeft - self.currentContainer.paddedLeft) - self.textIndent)/self.fontWidth)
		if wrapwidth < 1: wrapwidth = 1
		lines = textwrap.wrap(spaceLead + text, wrapwidth,drop_whitespace=False)
		if len(lines) > floatRightLines:
			lines1 = lines[:floatRightLines]
			lines2 = lines[floatRightLines:]
			self.resetFloatRight()
			text2 = ''.join(lines2)
			wrapwidth = int((self.currentContainer.contentWidth - self.textIndent) /self.fontWidth)
			lines2 = textwrap.wrap(text2, wrapwidth,drop_whitespace=False)
			lines = lines1 + lines2
			
		for x in range(1,len(lines)):
			lines[x] = lines[x].lstrip()
		
		return lines
		
	def addText(self,text,color=None,button=None,bold=False,pre=''):
		if not text: return
		text = ''.join(unicode.splitlines(self.decode(text)))
		lines = self.wrap(text,pre)
		rows = len(lines)
		height = (self.fontHeight * rows) or self.fontHeight
		lastLineLen = 0
		if lines: lastLineLen = len(lines[-1])
			
		text = '[CR]'.join(lines)
		if self.link:
			color = self.linkColor
			button = self.link
		if button:
			if not text.strip():
				button = None
				color = None
		ID = None
		child = None
		heightOffset = self.textAttributes.get('heightOffset',0)
		if text.strip():
			self.leftIsEmpty = False
			if text.strip().isdigit(): text = '[B][/B]' + text
			if self.textHasMod('bold'): bold = True
			self.contentStarted = True
			
			x = self.currentContainer.paddedLeft+self.fontXOff + self.textIndent
			if self.lastImageBottom and not self.floatRightBottom and not self.floatLeftLines:
				y = self.lastImageBottom - self.fontHeight
				if rows > 1:
					self.lastImageBottom = 0
					self.currentContainer.yindex = y
			else:
				y = self.currentContainer.yindex+self.fontYOff+heightOffset
			
			if button:
				ID, onleft, onright = self.getNextButtonIDs(button,y,height+5)
				but = RenderButton(x=x, y=y, w=self.currentContainer.contentWidth, h=height)
				but.id=ID
				but.onLeft=onleft
				but.onRight=onright
				but.bold=bold
				but.textOffsetX=-1
				but.setTextColor(color)
				but.text=text
				but.setFont(self.font)
				self.currentContainer.addChild(but)
				child = but
			else:
				tb = RenderTextbox(x=x,y=y,w=self.currentContainer.contentWidth,h=height)
				tb.bold=bold
				tb.setTextColor(color)
				tb.text=text
				tb.setFont(self.font)
				self.currentContainer.addChild(tb)
				child = tb

		if self.contentStarted:
			self.currentContainer.yindex += height - self.fontHeight
			self.currentContainer.setXIndex(int(self.currentContainer.paddedLeft + (lastLineLen * self.fontWidth)))
			if rows > 1:
				self.currentContainer.updateContentMaxX(self.currentContainer.right())
			else:
				if child: child.width = int(lastLineLen * self.fontWidth)
			self.currentContainer.updateMaxY(self.yindex + self.fontHeight)
		return child
	
	def addImage(self,tag,width=20,height=20,ratio='keep',button=None,texture=None,textureborder='',text='',textcolor='00000000',alignx='left',aligny='top',margin=(0,0,0,0)):
		if texture:
			url = texture
		else:
			src = tag.get('src','').strip()
			if not src: return
			url = urlparse.urljoin(self.url, src)
			if url.endswith('.gif'):
				cached = xbmcutil.getAndCacheImage(url, CACHE_PATH)
				dst = xbmcutil.localCachePath(cached, CACHE_PATH)[:-4] + '.png'
				url = imageops.gifToPng(url, dst)
			
		if texture:
			pass
		elif tag.get('width') and tag.get('height'):
			try:
				width = int(tag['width'].replace('px',''))
				height = int(tag['height'].replace('px',''))
				if not width or not height: raise Exception('Zero Width/Height')
				ratio = 'stretch'
			except:
				LOG('Bad Image Width/Height: w(%s) h(%s)' % (tag.get('width'),tag.get('height')))
		elif url in self.imageInfos:
			info = self.imageInfos[url]
			if info['type']:
				ratio = 'stretch'
				width = info['w']
				height = info['h']
		#if '?' in url: url += '&image_fix=%s' % time.time()		
		if width > self.currentContainer.contentWidth and not texture:
			height = int((self.currentContainer.contentWidth/float(width)) * height)
			width = self.currentContainer.contentWidth
		
		self.contentStarted = True
		if self.currentContainer.xindex + width > self.currentContainer.contentRight():
			self.newLine()
		if self.center and self.leftIsEmpty:
			self.currentContainer.setXIndex(self.currentContainer.paddedLeft + ((self.currentContainer.contentWidth - width) / 2))
		self.leftIsEmpty = False
		float_ = self.getTagFloat(tag)
		if float_ == 'right':
			x = self.currentContainer.contentRight() - (width + margin[3] + margin[1])
		else:
			x=self.currentContainer.xindex + margin[3]
		y=self.currentContainer.yindex + margin[0]
		ID = None
		heightWithMargin = height + margin[0] + margin[2]
		if button:
			ID, onleft, onright = self.getNextButtonIDs(button,y,heightWithMargin)
			url = url.format(id=ID)
		img = RenderImage(x=x, y=y, w=width, h=height)
		img.texture=url
		img.border=textureborder
		img.link=self.link
		img.ratio=ratio
		self.currentContainer.addChild(img)
		img.float = float_
		if button:
			if button.get('type') == 'EMBED:VIDEO':
				vw = RenderVideoWindow(x=x, y=y, w=width, h=height)
				vw.linkedButton = ID
				self.currentContainer.addChild(vw)

			but = RenderButton(x=x, y=y, w=width, h=height)
			but.id=ID
			but.onLeft=onleft
			but.onRight=onright
			but.textureFocus='web-viewer-red-border.png'
			but.alignX=alignx
			but.alignY=aligny
			but.textureFocusBorder=2
			but.setTextColor(textcolor)
			but.text=text
			but.setFont(self.font)
			self.currentContainer.addChild(but)
			but.float = float_
		imageBottom = self.currentContainer.yindex + heightWithMargin
		if float_ == 'left':
			self.setFloatLeft(self.currentContainer,width + margin[3] + margin[1], heightWithMargin)
			self.currentContainer.setXIndex(width  + margin[3] + margin[1], add=True)
		elif float_ == 'right':
			self.setFloatRight(self.currentContainer, x - margin[3], imageBottom)
		else:
			if imageBottom > self.lastImageBottom: self.lastImageBottom = imageBottom
			self.currentContainer.updateMaxY(imageBottom)
			self.currentContainer.setXIndex(width  + margin[3] + margin[1], add=True)
		return ID
	
	def setFloatLeft(self,container,width,height):
		self.floatLeftLines = int(math.ceil(height / float(self.fontHeight)))
		imageBottom = container.yindex + height
		if imageBottom > self.floatLeftBottom: self.floatLeftBottom = imageBottom
		if container.xindex > container.paddedLeft:
			self.lastImageLeft = container.xindex
		else:
			self.lastImageRight = container.xindex + width
		container.updateMaxY(imageBottom)
		
	def setFloatRight(self,container,left,bottom):
		if bottom > self.floatRightBottom: self.floatRightBottom = bottom
		self.floatRightLeft = left
		
	def drawImage(self,texture,x,y,w,h,ratio='keep',textureborder='',diffuse=''):
		img = RenderImage(x=x, y=y, w=w, h=h)
		img.texture=texture
		img.border=textureborder
		img.diffuse=diffuse
		img.ratio=ratio
		self.currentContainer.addChild(img)

class WebViewer:
	def __init__(self):
		self.fontInstalled = self.installFont()
		self.backgroundWindow = None
		self.renderer = WebPageRenderer(None)
		self.history = None
		self.progress = None
		self.progressLastLines = ('','','')
		self.progressLastPct = 0
		self.progressIncrement = 1
		self.historyOffset = 0
		self.windowXMLFile = None

	def __enter__(self):
		return self
	
	def __exit__(self,etype, evalue, traceback):
		self.end()
		
	def installFont(self):
		go = True
		fontPath = os.path.join(xbmc.translatePath(ADDON.getAddonInfo('path')),'resources','fonts')
		if fontmanager.isInstalled():
			install_update = 'update'
			if fontmanager.compareFont(os.path.join(fontPath,'WebViewer-Font-720p.xml')): return go
		else:
			install_update = 'install'
			
		yesno = xbmcgui.Dialog().yesno('Font Install','Web Viewer 2 requires a font %s.' % install_update,'Install Now?')
		if yesno:
			try:
				fm = fontmanager.FontManager([os.path.join(fontPath,'WebViewer-Font-720p.xml')],[os.path.join(fontPath,'WebViewer-DejaVuSansMono.ttf'),os.path.join(fontPath,'WebViewer-DejaVuSansMono-Bold.ttf')])
				fm.install()
				LOG('! REFRESHING XBMC SKIN !')
				xbmc.executebuiltin('ReloadSkin()')
				xbmc.sleep(2000)
				xbmcgui.Dialog().ok('Success','Fonts installed!')
			except:
				xbmcgui.Dialog().ok('Failed','Fonts installation failed!')
				import traceback
				traceback.print_exc()
				go = False
		else:
			go = False
		return go
	
	def startProgress(self):
		self.progress = xbmcgui.DialogProgress()
		self.progress.create('Getting Page','Starting...')
	
	def updateProgress(self,pct,line1=None,line2=None,line3=None):
		if not self.progress: return
		self.progressLastPct = pct
		l = self.progressLastLines
		l = (line1 !=None and line1 or l[0],line2 !=None and line2 or l[1],line3 !=None and line3 or l[2])
		self.progressLastLines = l
		self.progress.update(int(pct),l[0],l[1],l[2])
		if self.progress.iscanceled():
			self.close()
			self.endProgress()
	
	def setProgressIncrement(self,inc):
		self.progressIncrement = inc
		
	def updateProgressIncremental(self,line1=None,line2=None,line3=None):
		self.updateProgress(self.progressLastPct + self.progressIncrement,line1=line1,line2=line2,line3=line3)
		
	def endProgress(self):
		if self.progress: self.progress.close()
		self.progress = None
	
	def openBackground(self):
		self.backgroundWindow = xbmcgui.WindowXML('web-viewer-background.xml',ADDON.getAddonInfo('path'),'Default')
		self.backgroundWindow.show()
		
	def close(self):
		self.done = True
		if self.window: self.window.close()
	
	def start(self):
		if not self.fontInstalled: return False
		self.openBackground()
		self.webreader = WebReader()
		self.video = video.WebVideo()
		self.window = None
		self.done = False
		self.url = None
		self.webPage = None
		#startURL = 'http://www.google.com'
		#startURL = 'http://forum.xbmc.org/showthread.php?tid=85018&action=lastpost'
		#startURL = 'http://forum.xbmc.org'
		#startURL = 'http://playerones.geekandsundry.com'
		startURL = 'file://' + os.path.join(xbmc.translatePath(ADDON.getAddonInfo('path')),'resources','default.html')
		#startURL = 'http://guistuff.com/css/css_imagetech1.html'
		self.nextPage(startURL)
		self.history = URLHistory(HistoryLocation(startURL))
		while not self.done:
			self.openViewer()
		
	def submitForm(self,button_data,control_tags):
		tag = button_data.get('tag')
		idx = 0
		for c in control_tags:
			if c.get('type') == 'sumbit':
				if tag == c: break
				idx+=1
		webPage = self.webreader.submitForm(button_data.get('form'), idx, control_tags)
		if not webPage: return
		self.nextPage(webPage)
				
	def goBack(self,y_pos):
		if not self.history.canGoBack(): return
		self.history.current().line = y_pos
		h = self.history.goBack(y_pos)
		self.historyOffset = h.line
		self.nextPage(h.url)
		
	def nextPage(self,url,y_pos=0,history=None):
		self.startProgress()
		if history and history.renderFile:
			self.updateProgress(95, 'Using Cached Page')
			self.windowXMLFile = history.renderFile
			#update renderer with forms and button data
		else:
			if history: url = history.url
			try:
				self.updateProgress(5, 'Fetching Web Page')
				if isinstance(url,ResponseData):
					self.webPage = url
				else:
					self.webPage = self.webreader.getWebPage(url)
				if self.history:
					current = self.history.current()
					current.setRenderFile(self.windowXMLFile)
					self.history.addURL(HistoryLocation(self.webPage.url))
				if not self.webPage.hasText():
					if self.webPage.content.startswith('image'):
						self.updateProgress(30, 'Getting Image Info')
						width = height = ''
						try:
							itype,w,h = imageinfo.getImageInfo(self.webPage.response)
							if itype:
								width = ' width="%s"' % w
								height = ' height="%s"' % h
						except:
							pass
						self.webPage.data = '<html><head></head><body><img src="%s"%s%s></body></html>' % (self.webPage.url,width,height)
					else:
						self.endProgress()
						return
			except:
				self.endProgress()
				raise
			self.renderPage()
			
		if self.window:
			self.window.close()
			del self.window
			self.window = None
		else:
			self.endProgress()
		
	def renderPage(self):
		try:
			start = time.time()
			self.renderer.reset(self.webPage.url)
			self.renderer.renderPage(self.webPage.data)
			#open('/home/ruuk/test.html','w').write(self.webPage.data)
			self.windowXMLFile = self.renderer.writeWindow()
			self.updateProgress(100, 'Done')
			duration = time.time() - start
			LOG('Page Rendered in %.2f seconds' % duration)
		finally:
			self.endProgress()
			
	def openViewer(self):
		self.window = WebWindow(self.windowXMLFile,ADDON.getAddonInfo('path'),'Default',renderer=self.renderer)
		self.window.doModal()
			
	def end(self):
		if self.backgroundWindow: self.backgroundWindow.close()
		self.endProgress()
		import threading
		LOG('Threads still running: %s' % (len(threading.enumerate()) - 1))

def doKeyboard(prompt,default='',hidden=False):
	keyboard = xbmc.Keyboard(default,prompt)
	keyboard.setHiddenInput(hidden)
	keyboard.doModal()
	if not keyboard.isConfirmed(): return None
	return keyboard.getText()

with WebViewer() as WV: WV.start()
