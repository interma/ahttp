#!/usr/bin/env python
#coding=utf-8

import re
from atcp_server import ATcpServer

#url dispatch use regex
def request_dispatch(connection):
	path = connection.path
	get = connection.GET
	post = connection.POST
	print "PATH:%s GET:%s POST:%s" % (path,get,post)
	
	router = [ \
		(r'/hello/.*', on_hello),\
		(r'/tryme/.*', on_tryme)\
			]
	
	for item in router:
		regex = item[0]
		func = item[1]
		if re.match(regex,path):
			content = func(path,get,post)
	if not content:
		content = 'ok'

	connection.fill_http_response(content)

def on_hello(path,get=None,post=None):
	content = "you visit %s,GET:%s" % (path,str(get))
	return content

def on_tryme(get,post=None):
	pass
	

server = ATcpServer(request_dispatch)
#server.run_loop(8100, "async", True)
server.run_loop()

