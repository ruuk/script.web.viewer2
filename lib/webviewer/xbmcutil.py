import os, urllib2
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

def getAndCacheImage(source,cache_path):
	cached = getCachedImagePath(source,cache_path)
	if cached: return cached
	return cacheImage(source,cache_path)
	
def getCachedImagePath(source,cache_path=None):
	f, ext = os.path.splitext(source)  # @UnusedVariable
	base = xbmc.getCacheThumbName(source)[:-4]
	fname = base + ext
	d = fname[0]
	path = os.path.join(XBMC_THUMB_PATH,d,fname)
	if os.path.exists(path): return path
	path = os.path.join(XBMC_THUMB_PATH,d,base + '.jpg')
	if os.path.exists(path): return path
	if cache_path:
		path = os.path.join(cache_path,fname)
		if os.path.exists(path): return path
	return None

def cacheImage(source,dest_path):
	fname = xbmc.getCacheThumbName(source)
	data = urllib2.urlopen(source).read()
	dest = os.path.join(dest_path,fname)
	with open(dest,'wb') as f:
		f.write(data)
	return dest

def localCachePath(fname,cache_path):
	base = os.path.basename(fname)
	return os.path.join(cache_path,base)
	