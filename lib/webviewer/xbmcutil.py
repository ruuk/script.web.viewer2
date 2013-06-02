import os
import xbmc

XBMC_THUMB_PATH = xbmc.translatePath('special://profile/Thumbnails')

def get_crc32( string ):
	string = string.lower()		
	bbytes = bytearray(string.encode())
	crc = 0xffffffff;
	for b in bbytes:
		crc = crc ^ (b << 24)		  
		for i in range(8):  # @UnusedVariable
			if (crc & 0x80000000 ):				 
				crc = (crc << 1) ^ 0x04C11DB7				
			else:
				crc = crc << 1;						
		crc = crc & 0xFFFFFFFF
		
	return '%08x' % crc

def getCachedImagePath(source):
	f, ext = os.path.splitext(source)  # @UnusedVariable
	base = xbmc.getCacheThumbName(source)[:-4]
	fname = base + ext
	d = fname[0]
	path = os.path.join(XBMC_THUMB_PATH,d,fname)
	if os.path.exists(path): return path
	path = os.path.join(XBMC_THUMB_PATH,d,base + '.jpg')
	if os.path.exists(path): return path
	return None
	