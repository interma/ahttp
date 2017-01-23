import threading
import time

global_cnt=0

def hello():
	global global_cnt
	global_cnt+=1
	print "hello from timer"
	t = threading.Timer(3.0, hello)
	t.start() # after 30 seconds, "hello, world" will be printed

hello()
while True:
	global_cnt+=1
	print "main:%d"%(global_cnt)
	time.sleep(2)
