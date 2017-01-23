#!/usr/bin/env python
#coding=utf-8

import sys
import re
import time
import tempfile
import threading
import torndb
from atcp_server import ATcpServer


db = torndb.Connection("host", "db","user","pass")
local_data_path = "/home/work/interma/python/tmp_file/"

"""
url dispatch use regex
"""
def request_dispatch(connection):
	path = connection.path
	get = connection.GET
	post = connection.POST
	print "PATH:%s GET:%s" % (path,get)

	if re.match(r'/filesend/.*', path):
		on_filesend(connection,path,get,post)
	else:
		content = "Running, you just visit %s<br />; Read <a href='#'>help here</a>" % (path)
		connection.fill_http_response(content, "text/html")
		server.fire_response(connection.connection.fileno());


"""
request based on http post:
	file_content
	file_path
	conf
	user
	pass
"""
def on_filesend(connection,path,get=None,post=None):
	if not post or not post.has_key('FILE'):
		content = "not post any thing"
		connection.fill_http_response(content)
		server.fire_response(connection.connection.fileno());
		return

	#parse request
	file_content = post['FILE']['content']
	file_path = post['file_path']
	conf = post['conf']
	if not conf.isdigit():
		pass
	else:
		conf = int(conf)
		
	#check user

	#write tmp file
	tmpfile = tempfile.mktemp(dir=local_data_path)
	file_object = open(tmpfile, 'w')
	file_object.write(file_content)
	file_object.close()

	#write db
	addr = connection.addr
	fileno = connection.connection.fileno()

	ident = "%s_%s_%d" % (addr[0],addr[1],fileno)
	now = time.strftime("%Y-%m-%d %X", time.localtime())
	sql = "insert into filesend(status,conf_id,ident,tmpfile,file_path,create_time) \
		  values(%d,%d,'%s','%s','%s','%s')" % \
		  (0, conf, ident, tmpfile, file_path, now)
	db.execute(sql)

def watch_sample():
	watch_run = True
	while watch_run:
		for fileno,connection in server.acnn_dict.items():
			content = str(fileno) + " wait so long, :-)"
			connection.fill_http_response(content)
			server.fire_response(fileno)
			#print "fire " + str(fileno)
			break
		time.sleep(20)	
	
"""
watch mysql row until noah task done
"""
def watch_connection():
	watch_run = True
	while watch_run:
		#noah_result: 0 init; 1 succ; 2 fail
		#status: 0 init; 1 launched; 2 done; 3 reported; -1 error;	
		sql = "select * from filesend where status=1 and noah_result > 0 "
		rows = db.query(sql)

		if not rows or len(rows) == 0:
			time.sleep(1)	
			continue
		
		for row in rows:
			noah_result = row['noah_result']
			if noah_result == 1:
				content = "succ"
			else:
				content = 'fail'

			ident = row['ident']
			ip,port,fileno = ident.split('_')
			fileno = int(fileno)

			if server.acnn_dict.has_key(fileno):
				connection = server.acnn_dict[fileno]
				addr = connection.addr
				if addr[0] == ip and int(addr[1]) == int(port):
					connection.fill_http_response(content)
					server.fire_response(fileno)

		sql = "update filesend set status=3 where status=0 and noah_result > 0 "
		db.execute(sql)


#global server instance
server = ATcpServer(request_dispatch)

watch_thread = threading.Thread(target=watch_connection)
watch_thread.setDaemon('True')
watch_thread.start()

#server.run_loop(8100, "async", False)
server.run_loop(8100, "async", True, 5*60)
db.close()


