
#	Points	Pixels	Ems	Percent
conversion = [
	(6,		8,		0.5,	50),
	(7,		9,		0.55,	55),
	(7,		10,		0.625,	62.5), # 7.5
	(8,		11,		0.7,	70),
	(9,		12,		0.75,	75),
	(10,	13,		0.8,	80),
	(10,	14,		0.875,	87.5), #10.5
	(11,	15,		0.95,	95),
	(12,	16,		1,		100),
	(13,	17,		1.05,	105),
	(13,	18,		1.125,	112.5), #13.5
	(14,	19,		1.2,	120),
	(14,	20,		1.25,	125), #14.5
	(15,	21,		1.3,	130),
	(16,	22,		1.4,	140),
	(17,	23,		1.45,	145),
	(18,	24,		1.5,	150),
	(20,	26,		1.6,	160),
	(22,	29,		1.8,	180),
	(24,	32,		2,		200),
	(26,	35,		2.2,	220),
	(27,	36,		2.25,	225),
	(28,	37,		2.3,	230),
	(29,	38,		2.35,	235),
	(30,	40,		2.45,	245),
	(32,	42,		2.55,	255),
	(34,	45,		2.75,	275),
	(36,	48,		3,		300)
]

def pxToPt(px):
	try:
		px = int(px)
	except:
		return 12
	
	if px < 8: return 6
	for s in conversion:
		if px == s[1]: return s[0]
	return 36

def emToPt(em):
	try:
		em = int(em)
	except:
		return 12
	
	last = 0
	if em < 0.5: return 6
	for s in conversion:
		if em > last and em <= s[2]:
			return s[0]
		last = s[2]
	return 36

def pctToPt(pct):
	try:
		pct = int(pct)
	except:
		return 12
	
	last = 0
	if pct < 50: return 6
	for s in conversion:
		if pct > last and pct <= s[3]:
			return s[0]
		last = s[3]
	return 36
