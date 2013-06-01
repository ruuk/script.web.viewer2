import os, sys
from distutils.version import StrictVersion
import xbmc, xbmcgui, xbmcvfs

LOG_PREFIX = 'FontManager'

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

def isInstalled():
	currentSkinPath = xbmc.translatePath('special://skin')
	if currentSkinPath.endswith(os.path.sep): currentSkinPath = currentSkinPath[:-1]
	currentSkin = os.path.basename(currentSkinPath)
	test = os.path.join(xbmc.translatePath('special://home'),'addons',currentSkin,'fonts','FontManager','Font.xml')
	return os.path.exists(test)
	
FBMod = '''		<!-- Forum Browser Fonts Mod -->
	 	<font>
			<name>ForumBrowser-font10</name>
			<filename>ForumBrowser-DejaVuSans.ttf</filename>
			<size>12</size>
		</font>
	 	<font>
			<name>ForumBrowser-font12</name>
			<filename>ForumBrowser-DejaVuSans.ttf</filename>
			<size>16</size>
		</font>
		<font>
			<name>ForumBrowser-font13</name>
			<filename>ForumBrowser-DejaVuSans.ttf</filename>
			<size>20</size>
		</font>
		<font>
			<name>ForumBrowser-font30</name>
			<filename>ForumBrowser-DejaVuSans.ttf</filename>
			<size>30</size>
		</font>
'''

class FontManager:
	def __init__(self,font_xmls=None,fonts=None):
		self.fontXMLs=font_xmls
		self.fonts = fonts
		self.localAddonsPath = os.path.join(xbmc.translatePath('special://home'),'addons')
		self.currentSkinPath = xbmc.translatePath('special://skin')
		if self.currentSkinPath.endswith(os.path.sep): self.currentSkinPath = self.currentSkinPath[:-1]
		self.currentSkin = os.path.basename(self.currentSkinPath)
		self.localSkinPath = os.path.join(self.localAddonsPath,self.currentSkin)
		
		localVersion = self.getSkinVersion(self.localSkinPath)
		currentVersion = self.getSkinVersion(self.currentSkinPath)
		
		if not os.path.exists(self.localSkinPath) or StrictVersion(localVersion) < StrictVersion(currentVersion):
			self.skinInstalledLocal = False
		else:
			self.skinInstalledLocal = True
		self.addFBFont = False
		
	def getSkinVersion(self,skin_path):
		addon = os.path.join(skin_path,'addon.xml')
		if not os.path.exists(addon): return '0.0.0'
		acontent = open(addon,'r').read()
		return acontent.split('<addon',1)[-1].split('version="',1)[-1].split('"',1)[0]
	
	def setPaths(self):
		self.res = '720p'
		test = os.path.join(self.localSkinPath,'720p','Font.xml')
		if not os.path.exists(test): self.res = '1080i'
		
		self.skinXMLPath = os.path.join(self.localSkinPath,self.res)
		self.fontsPath = os.path.join(self.localSkinPath,'fonts')
		
		self.fontXMLPath = os.path.join(self.skinXMLPath,'Font.xml')
		self.managerPath = os.path.join(self.fontsPath,'FontManager')
		self.modsPath = os.path.join(self.managerPath,'mods')
		self.fontXMLBackupPath = os.path.join(self.managerPath,'Font.xml')

	def copyTree(self,source,target,dialog=None):
		pct = 0
		mod = 5
		if not source or not target: return
		if not os.path.isdir(source): return
		sourcelen = len(source)
		if not source.endswith(os.path.sep): sourcelen += 1
		for path, dirs, files in os.walk(source): #@UnusedVariable
			subpath = path[sourcelen:]
			xbmcvfs.mkdir(os.path.join(target,subpath))
			for f in files:
				if dialog: dialog.update(pct,'',f)
				xbmcvfs.copy(os.path.join(path,f),os.path.join(target,subpath,f))
				pct += mod
				if pct > 100:
					pct = 95
					mod = -5
				elif pct < 0:
					pct = 5
					mod = 5
		
	def copyFile(self,source,dest):
		if os.path.exists(dest): xbmcvfs.delete(dest)
		xbmcvfs.copy(source,dest)
			
	def makeLocalCopy(self):
		yesno = xbmcgui.Dialog().yesno('No Local Copy','Skin ({0}) needs to be copied'.format(self.currentSkin),'to the local path.','Copy now?')
		if not yesno: return False
		dialog = xbmcgui.DialogProgress()
		dialog.create('Copying','Copying skin files...')
		try:
			self.copyTree(self.currentSkinPath,self.localSkinPath,dialog)
		except:
			err = ERROR('Failed to copy skin to user directory')
			xbmcgui.Dialog().ok('Failed','Failed to copy skin files:',err)
			return False
		finally:
			dialog.close()
		xbmcgui.Dialog().ok('Done','Skin files successfully copied.')
		return True
	
	def backupFontXML(self):
		source = self.fontXMLPath
		fbBackupPath = os.path.join(self.localSkinPath,self.res,'Font.xml.FBbackup')
		if os.path.exists(fbBackupPath):
			source = fbBackupPath
			self.addFBFont = True
			LOG('Forum Browser font mod detected.')
		fontcontents = open(source,'r').read()
		if not os.path.exists(self.fontXMLBackupPath):
			LOG('Creating backup of original Font.xml file: ' + source)
			open(self.fontXMLBackupPath,'w').write(fontcontents)
		
	def copyFiles(self):
		for f in self.fontXMLs:
			if self.res != '720p':
				new = f.replace('720p',self.res)
				if os.path.exists(new): f = new
			base = os.path.basename(f)
			self.copyFile(f, os.path.join(self.modsPath,base))
		for f in self.fonts:
			base = os.path.basename(f)
			self.copyFile(f, os.path.join(self.fontsPath,base))
			
	def modFontXML(self):
		with open(self.fontXMLBackupPath,'r') as f: xml = f.read()
		if self.addFBFont:
			xml = xml.replace('<font>',FBMod + '<font>',1)
		for fn in os.listdir(self.modsPath):
			with open(os.path.join(self.modsPath,fn),'r') as f: contents = f.read()
			xml = xml.replace('<font>',contents + '<font>',1)
		with open(self.fontXMLPath,'w') as f: f.write(xml)
		
	def isInstalled(self):
		self.setPaths()
		return os.path.exists(self.fontXMLBackupPath)
	
	def install(self):
		if not self.skinInstalledLocal:
			if not self.makeLocalCopy(): return False
		self.setPaths()
		if not os.path.exists(self.modsPath): os.makedirs(self.modsPath)
		self.backupFontXML()
		self.copyFiles()
		self.modFontXML()
		return True
	
	def unInstall(self):
		if not self.isInstalled(): return #Paths set in this call as well
		if not os.path.exists(self.fontXMLBackupPath): return
		self.copyFile(self.fontXMLBackupPath,self.fontXMLPath)
		#TODO: Remove the files and dirs
		
