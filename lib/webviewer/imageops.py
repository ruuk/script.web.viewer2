import os
try:
	from PIL import Image  # @UnresolvedImport
except:
	Image = None
	
def createOffsetMask(w,h,xoff,yoff,outfile):
	if not Image: return None
	xoff = abs(xoff)
	yoff = abs(yoff)
	size = (w + xoff,h + yoff)
	img = Image.new("RGBA", size, (0,0,0,0))
	corner = Image.new("RGB", (w,h), (255,255,255,255))
	
	img.paste(corner,(xoff,yoff))
	img.save(outfile)
	return size

def gifToPng(src,dst):
	if not Image: return src
	if os.path.exists(dst): return dst
	img = Image.open(src)
	img = img.convert('RGBA')
	img.save(dst,'PNG')
	return dst