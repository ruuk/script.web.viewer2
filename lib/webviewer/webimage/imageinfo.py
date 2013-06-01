import urllib2, struct
import threadpool

import ReseekFile

WORK_QUEUE = None

def infoWorker(info):
	try:
		info['type'],info['w'],info['h'] = getImageURLInfo(info['url'])
	except:
		print 'Worker failed to get image info'
	return info
		
def getImageURLInfos(urls,threaded=True,progress=None):
	infos = {}
	if not threaded:
		for url in urls:
			if url in infos: continue
			info = {'url':url}
			try:
				info['type'],info['w'],info['h'] = getImageURLInfo(url)
			except:
				continue
			infos[url] = info
		return infos
			
	pool = threadpool.ThreadPool(4)
	req = []
	for url in urls:
		if url in infos: continue
		info = {'url':url,'w':None,'h':None,'type':None}
		req.append(info)
		
	requests = threadpool.makeRequests(infoWorker, req)
	[pool.putRequest(req) for req in requests]
	results = pool.wait(return_results=True,progress=progress)
	pool.dismissWorkers()
	infos = {}
	for info in results:
		infos[info['url']] = info
	return infos
		
def getImageURLInfo(url):
	imgdata = urllib2.urlopen(url)
	return getImageInfo(imgdata)

def getImageInfo(datastream):
	datastream = ReseekFile.ReseekFile(datastream)
	data = str(datastream.read(30))
	size = len(data)
	height = -1
	width = -1
	content_type = ''

	# handle GIFs
	if (size >= 10) and data[:6] in ('GIF87a', 'GIF89a'):
		# Check to see if content_type is correct
		content_type = 'image/gif'
		w, h = struct.unpack("<HH", data[6:10])
		width = int(w)
		height = int(h)

	# See PNG 2. Edition spec (http://www.w3.org/TR/PNG/)
	# Bytes 0-7 are below, 4-byte chunk length, then 'IHDR'
	# and finally the 4-byte width, height
	elif ((size >= 24) and data.startswith('\211PNG\r\n\032\n')
		  and (data[12:16] == 'IHDR')):
		content_type = 'image/png'
		w, h = struct.unpack(">LL", data[16:24])
		width = int(w)
		height = int(h)

	# Maybe this is for an older PNG version.
	elif (size >= 16) and data.startswith('\211PNG\r\n\032\n'):
		# Check to see if we have the right content type
		content_type = 'image/png'
		w, h = struct.unpack(">LL", data[8:16])
		width = int(w)
		height = int(h)

	# handle JPEGs
	elif (size >= 2) and data.startswith('\377\330'):
		content_type = 'image/jpeg'
		datastream.seek(0)
		datastream.read(2)
		b = datastream.read(1)
		try:
			while (b and ord(b) != 0xDA):
				while (ord(b) != 0xFF): b = datastream.read(1)
				while (ord(b) == 0xFF): b = datastream.read(1)
				if (ord(b) >= 0xC0 and ord(b) <= 0xC3):
					datastream.read(3)
					h, w = struct.unpack(">HH", datastream.read(4))
					break
				else:
					datastream.read(int(struct.unpack(">H", datastream.read(2))[0])-2)
				b = datastream.read(1)
			width = int(w)
			height = int(h)
		except struct.error:
			pass
		except ValueError:
			pass

	return content_type, width, height
