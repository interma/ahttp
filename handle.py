
id = 0;
sort_id = 0;
for line in open('import.txt'):
	line = line.strip()
	print "%d:%d:%s" % (id,sort_id,line)
	id += 1
	sort_id += 10
