#!/usr/bin/env python
#coding=utf-8

import socket
import select
import time
import logging
import urlparse
import threading


#==conf==
READ_CHUNK_SIZE = 1024*1024 
BAKLOG_SIZE = 1024
SERVER_TAG = "interma atcpserver 0.1" 
#logger
logger = logging.getLogger('interma.atcpserver')
#fh = logging.FileHandler("sample.log")
#fh.setLevel(logging.DEBUG)
console = logging.StreamHandler()  
console.setLevel(logging.DEBUG)  
formatter = logging.Formatter('%(levelname)s - %(asctime)s - %(thread)d - %(name)s[%(filename)s:%(lineno)d] - %(message)s')
console.setFormatter(formatter)  

logger.setLevel(logging.DEBUG)
logger.addHandler(console)

#==util func==
#form-data; name="upfile"; filename="post.py"
def parse_one_line_header(line):
    parts = _parseparam(';' + line)
    key = next(parts)
    pdict = {}
    for p in parts:
        i = p.find('=')
        if i >= 0:
            name = p[:i].strip().lower()
            value = p[i + 1:].strip()
            if len(value) >= 2 and value[0] == value[-1] == '"':
                value = value[1:-1]
                value = value.replace('\\\\', '\\').replace('\\"', '"')
            pdict[name] = value
    return key, pdict
def _parseparam(s):
    while s[:1] == ';':
        s = s[1:]
        end = s.find(';')
        while end > 0 and (s.count('"', 0, end) - s.count('\\"', 0, end)) % 2:
            end = s.find(';', end + 1)
        if end < 0:
            end = len(s)
        f = s[:end]
        yield f.strip()
        s = s[end:]

#a=123&b=456
def parse_qs(qsdata):
	qs = dict( (k, v if len(v)>1 else v[0] ) for k, v in urlparse.parse_qs(qsdata).iteritems() )
	return qs

#==main class==
"""
async tcp server
"""
class ATcpServer:
	def __init__(self, req_cb):
		self.epoll = select.epoll() 
		self.acnn_dict = {}		# fileno=>AConnection
		self.req_cb = req_cb	# on_requerst callback 
		self.watch_stop = False # watch thread run tag
		self.alive_time = 0
	
	"""
		auto clean connection
	"""
	def watch_connection(self):
		while not self.watch_stop:
			logger.debug( ("watched %d fileno") % (len(self.acnn_dict)) )
			for fileno,acnn in self.acnn_dict.items():
				if self.alive_time > 0 and time.time()-acnn.ts > self.alive_time:
					self.epoll.unregister(fileno)
					acnn.connection.close()
					del self.acnn_dict[fileno]
					logger.debug( ("fileno[%d] timeout cleaned") % (fileno) )
			time.sleep(1)	
	
	def fire_response(self, fileno):
		self.epoll.modify(fileno, select.EPOLLOUT)
	
	def run_loop(self, port=8100, mode="sync", watch_thread=False, alive_time=300):
		serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		serversocket.bind(('0.0.0.0', port))
		serversocket.listen(BAKLOG_SIZE) # 太小导致client连接不上,如ab测试时发现
		serversocket.setblocking(0)
		self.epoll.register(serversocket.fileno(), select.EPOLLIN)
		
		if watch_thread:
			self.alive_time = alive_time
			watch_thread = threading.Thread(target=self.watch_connection)
			watch_thread.start()
		
		#begin event loop
		try:
			while True:
				events = self.epoll.poll(1)
				for fileno, event in events:
					#server accept 
					if fileno == serversocket.fileno():
						connection, address = serversocket.accept()
						address = connection.getpeername()
						connection.setblocking(0)
						self.epoll.register(connection.fileno(), select.EPOLLIN)
						
						#client connection
						acnn = AConnection(connection, address, self)
						self.acnn_dict[connection.fileno()] = acnn

						logger.debug( ("fileno[%d], %s connected") % (connection.fileno(),address[0]) )
					#read client and parse
					elif event & select.EPOLLIN:
						acnn = self.acnn_dict[fileno]

						chunk = acnn.connection.recv(READ_CHUNK_SIZE)
						ret = acnn.parse_http_request(chunk)
						if ret == 'DONE':
							#parse http request over
							self.epoll.modify(fileno, 0)
							self.req_cb(acnn) # call user callback
							if mode == "sync":
								self.epoll.modify(fileno, select.EPOLLOUT)
							else:
								#use fire_request, modify select.EPOLLOUT in future
								pass
						elif ret == 'NOT_YET':
							#continue read chunk
							pass
						elif ret == 'ERROR':
							#ignore this connection
							logger.debug( ("fileno[%d], ignore connection %s") % (fileno, acnn.addr) )

							self.epoll.unregister(fileno)
							acnn.connection.close()
							del self.acnn_dict[fileno]

					#send request
					elif event & select.EPOLLOUT:
						acnn = self.acnn_dict[fileno]

						byteswritten = acnn.connection.send(acnn.res_buf)
						acnn.res_buf = acnn.res_buf[byteswritten:]

						if len(acnn.res_buf) == 0:
							#There is no need to register interest in HUP events. 
							#They are always indicated on sockets that are registered with the epoll object.
							self.epoll.modify(fileno, 0)
							logger.debug( ("fileno[%d] send over") % (fileno) )
							try:
								acnn.connection.shutdown(socket.SHUT_RDWR)
							except socket.error:
								logger.warning( ("fileno[%d] socket.error") % (fileno) )
								pass
					#disconnect or error	
					elif event & select.EPOLLHUP:
						acnn = self.acnn_dict[fileno]
						logger.debug( ("fileno[%d], %s disconnected") % (fileno, acnn.addr) )

						self.epoll.unregister(fileno)
						acnn.connection.close()
						del self.acnn_dict[fileno]
		finally:
			self.epoll.unregister(serversocket.fileno())
			self.epoll.close()
			serversocket.close()
			if watch_thread:
				self.watch_stop = True

		print "cannot run here?"



class AConnection:
	def __init__(self, connection, address, server):
		self.server = server
		self.connection = connection
		self.addr = address		#client (ip,port)
		self.req_buf = ''		#request buf
		self.req_header = {}    #request http header
		self.path = '' 
		self.POST = {}
		self.GET = {}
		self.ts = time.time()

		self.res_buf = ''		#response buf

	def fill_http_response(self,content,content_type="text/plain"):
		response  = "HTTP/1.0 200 OK\r\nDate: Mon, 20 Dec 1982 01:01:01 GMT\r\n"
		response += "Server: %s\r\n" % (SERVER_TAG)
		response += "Content-Type: %s\r\nContent-Length: %d\r\n\r\n" % (content_type,len(content))
		response += content

		self.res_buf = response

	def parse_http_request(self,chunk):
		EOL1 = b'\r\n\r\n'
		self.req_buf += chunk

		#parse http header
		if not self.req_header and EOL1 in self.req_buf:
			data = self.req_buf
			eol = data.find("\r\n")
			start_line = data[:eol]
			headers = data[eol:]
			body_pos = headers.find(EOL1)

			self.req_buf = headers[body_pos+4:] #consume header
			headers = headers[:body_pos]

			ret = self._parse_header(start_line,headers)
			if ret == 'ERROR':
				return ret
			#print self.req_buf

		#parse http body
		content_length = self.req_header.get("content-length")
		if content_length:
			#may POST
			#print content_length
			#print len(self.req_buf)
			if len(self.req_buf) >= int(content_length):
				#print self.req_buf
				#print self.req_buf.split('------------------------------')

				ret = self._parse_post_body(self.req_header,self.req_buf)
				return ret
		else:
			#may GET
			return "DONE"

		return "NOT_YET"

	def _parse_post_body(self,header,body):
		method = header['Method']
		content_type = header['content-type']
		if method != 'POST':
			logger.warning("parse_post_body not support method[%s]" % (method))
			return "DONE"

		if content_type.startswith("application/x-www-form-urlencoded"):
			#print body
			qs = parse_qs(body.strip())
			for key, val in qs.items():
				if val:
					self.POST[key] = val
		elif content_type.startswith("multipart/form-data"):
			fields = content_type.split(";")
			for field in fields:
				k, sep, v = field.strip().partition("=")
				if k == "boundary" and v:
					self._parse_multipart_form_data(v, body)
					#print self.POST
					break
			else:
				logger.warning("parse_post_body invalid multipart/form-data")
		else:
			logger.warning("parse_post_body unknown content-type[%s]" % (method))
		
		return "DONE"

	def _parse_multipart_form_data(self, boundary, data):
		if boundary.startswith(b'"') and boundary.endswith(b'"'):
			boundary = boundary[1:-1]
		final_boundary_index = data.rfind(b"--" + boundary + b"--")
		if final_boundary_index == -1:
			logger.warning("parse_post_body Invalid multipart/form-data: no final boundary")
			return
		parts = data[:final_boundary_index].split(b"--" + boundary + b"\r\n")
		for part in parts:
			if not part:
				continue

			#print part
			#continue

			eoh = part.find(b"\r\n\r\n")
			if eoh == -1:
				logger.warning("parse_post_body Invalid multipart/form-data: no final boundary")
				continue
			
			head = part[:eoh]
			value = part[eoh + 4:-2]
			part_headers = {}

			items = head.split('\n')
			for header_line in items:
				header_line = header_line.strip()
				if header_line == '':
					continue
				key,val = header_line.split(":",1)
				if key != '':
					part_headers[key.lower()] = val.strip()

			disp_header = part_headers["content-disposition"]
			
			#print disp_header
			disposition, disp_params = parse_one_line_header(disp_header)
			if disposition != "form-data" or not part.endswith(b"\r\n"):
				logger.warning("parse_post_body Invalid multipart/form-data")
				continue
			if not disp_params.get("name"):
				logger.warning("parse_post_body multipart/form-data value missing name")
				continue
			name = disp_params["name"]
			if disp_params.get("filename"):
				ctype = part_headers["content-type"]
				self.POST['FILE'] = {}
				self.POST['FILE']['filename'] = disp_params["filename"] 
				self.POST['FILE']['content_type'] = ctype 
				self.POST['FILE']['content'] = value 
			else:
				self.POST[name] = value #TODO not support array


	def _parse_header(self,start_line,headers):
		try:
			method, uri, version = start_line.split(" ")
		except ValueError:
			logger.warning("parse_header Malformed HTTP request line")
			return 'ERROR'
		
		if not version.startswith("HTTP/"):
			logger.warning("parse_header Malformed HTTP version in HTTP Request-Line")
			return 'ERROR'

		self.req_header['Method'] = method
		self.req_header['Uri'] = uri

		parse_result = urlparse.urlparse(uri)
		self.path = parse_result.path
		self.GET = parse_qs(parse_result.query)  

		#print start_line
		#print headers
		items = headers.split('\n')
		for header_line in items:
			header_line = header_line.strip()
			if header_line == '':
				continue
			key,val = header_line.split(":",1)
			if key != '':
				#header不区分大小写
				self.req_header[key.lower()] = val.strip()
		#print self.addr
		#print self.req_header
		logger.info( ("request header: %s") % (self.req_header) )

		return 'OK'

#==test==
if __name__ == '__main__':
	cnt = 1
	def on_request(connection):
		global cnt
		content = ("request %d from %s") % (cnt, connection.addr, ) 
		print "\tPATH:%s GET:%s POST:%s" % (connection.path,connection.GET,connection.POST)
		connection.fill_http_response(content)
		cnt += 1

	server = ATcpServer(on_request)
	#server.run_loop(8100, "async", True)
	server.run_loop()
	pass

