import threading
import time

def func1():
	for i in range(0,5):
		print 'func(1) passed to Thread'
		time.sleep(2)
def func2():
	for i in range(0,5):
		print 'func(2) passed to Thread'
		time.sleep(1)
def func3():
	for i in range(0,5):
		print 'func(2) passed to Thread'
		time.sleep(1)

class C:
	def func(self):
		print 'class passed to Thread'
		time.sleep(1)

	def run(self):
		t4 = threading.Thread(self.func())
 
t1 = threading.Thread(target=func1)
t2 = threading.Thread(target=func2)
t3 = threading.Thread(target=func3)
#t1.start()
#t2.start()
#t3.start()

c = C()
c.run()
