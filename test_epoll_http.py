import socket, select


#====util func
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

def _parse_header(line):
    """Parse a Content-type like header.

    Return the main content-type and a dictionary of options.

    """
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

#====end util func

EOL1 = b'\r\n\r\n'
#EOL2 = b'\n\r\n'
response  = b'HTTP/1.0 200 OK\r\nDate: Mon, 1 Jan 1996 01:01:01 GMT\r\n'
response += b'Content-Type: text/plain\r\nContent-Length: 13\r\n\r\n'
response += b'Hello, world!'

serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
serversocket.bind(('0.0.0.0', 8100))
serversocket.listen(5)
serversocket.setblocking(0)

epoll = select.epoll() #global epoll
epoll.register(serversocket.fileno(), select.EPOLLIN)

connections_dict = {} # fd=>Connection
class Connection:
	def __init__(self,fd,address):
		self.fd = fd
		self.req_buf = ''
		self.req_header = {}
		self.addr = address[0]
		self.POST = {}

	def _parse_multipart_form_data(self, boundary, data):
		if boundary.startswith(b'"') and boundary.endswith(b'"'):
			boundary = boundary[1:-1]
		final_boundary_index = data.rfind(b"--" + boundary + b"--")
		if final_boundary_index == -1:
			gen_log.warning("Invalid multipart/form-data: no final boundary")
			return
		parts = data[:final_boundary_index].split(b"--" + boundary + b"\r\n")
		for part in parts:
			if not part:
				continue

			#print part
			#continue

			eoh = part.find(b"\r\n\r\n")
			if eoh == -1:
				gen_log.warning("multipart/form-data missing headers")
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
					part_headers[key] = val.strip()

			disp_header = part_headers["Content-Disposition"]
			
			disposition, disp_params = _parse_header(disp_header)
			if disposition != "form-data" or not part.endswith(b"\r\n"):
				gen_log.warning("Invalid multipart/form-data")
				continue
			if not disp_params.get("name"):
				gen_log.warning("multipart/form-data value missing name")
				continue
			name = disp_params["name"]
			if disp_params.get("filename"):
				ctype = part_headers["Content-Type"]
				self.POST['FILE'] = {}
				self.POST['FILE']['filename'] = disp_params["filename"] 
				self.POST['FILE']['content_type'] = ctype 
				self.POST['FILE']['content'] = value 
			else:
				self.POST[name] = value #not support array
				#arguments.setdefault(name, []).append(value)

	def _parse_post_body(self,header,body):
		method = header['Method']
		content_type = header['Content-Type']
		if method != 'POST':
			print "only support post"
			return

		if content_type.startswith("application/x-www-form-urlencoded"):
			print "only support from-data"
			return 
			uri_arguments = parse_qs_bytes(native_str(body), keep_blank_values=True)
			for name, values in uri_arguments.items():
				if values:
					arguments.setdefault(name, []).extend(values)
		elif content_type.startswith("multipart/form-data"):
			fields = content_type.split(";")
			for field in fields:
				k, sep, v = field.strip().partition("=")
				if k == "boundary" and v:
					self._parse_multipart_form_data(v, body)
					print self.POST
					break
			else:
				gen_log.warning("Invalid multipart/form-data")
	


	def _parse_header(self,start_line,headers):
		try:
			method, uri, version = start_line.split(" ")
		except ValueError:
			raise Exception("Malformed HTTP request line")
		if not version.startswith("HTTP/"):
			raise Exception("Malformed HTTP version in HTTP Request-Line")
		self.req_header['Method'] = method
		self.req_header['Uri'] = uri
		#print start_line
		#print headers
		items = headers.split('\n')
		for header_line in items:
			header_line = header_line.strip()
			if header_line == '':
				continue
			key,val = header_line.split(":",1)
			if key != '':
				self.req_header[key] = val.strip()
		print self.addr
		print self.req_header

	def parse_http_request(self,chunk):
		self.req_buf += chunk
		#if EOL1 in self.req_buf or EOL2 in self.req_buf:
		content_length = self.req_header.get("Content-Length")
		if not content_length and EOL1 in self.req_buf:
			#parse header
			data = self.req_buf
			eol = data.find("\r\n")
			start_line = data[:eol]
			headers = data[eol:]
			body_pos = headers.find(EOL1)

			self.req_buf = headers[body_pos+4:] #consume header
			headers = headers[:body_pos]

			self._parse_header(start_line,headers)

			#print self.req_buf

		content_length = self.req_header.get("Content-Length")
		if content_length:
			#print content_length
			#print len(self.req_buf)
			if len(self.req_buf) >= int(content_length):
				#print self.req_buf
				#print self.req_buf.split('------------------------------')

				self._parse_post_body(self.req_header,self.req_buf)

				#parse body
				epoll.modify(fileno, select.EPOLLOUT)


connections = {}; requests = {}; responses = {}

def parse_http_request(fileno):
	global connections
	global requests
	global epoll
	if EOL1 in requests[fileno] or EOL2 in requests[fileno]:
		epoll.modify(fileno, select.EPOLLOUT)
		print('-'*40 + '\n' + requests[fileno].decode()[:-2])

try:
   while True:
	  events = epoll.poll(1)
	  for fileno, event in events:
		 if fileno == serversocket.fileno():
			connection, address = serversocket.accept()
			connection.setblocking(0)
			epoll.register(connection.fileno(), select.EPOLLIN)
			
			fd = connection.fileno()
			cnn=Connection(fd, address)
			connections_dict[fd] = cnn

			connections[connection.fileno()] = connection
			requests[connection.fileno()] = b''
			responses[connection.fileno()] = response
		 elif event & select.EPOLLIN:
			chunk = connections[fileno].recv(1024)
			requests[fileno] += chunk
			#parse_http_request(fileno)
			fd = connection.fileno()
			connections_dict[fd].parse_http_request(chunk)

		 elif event & select.EPOLLOUT:
			byteswritten = connections[fileno].send(responses[fileno])
			responses[fileno] = responses[fileno][byteswritten:]
			if len(responses[fileno]) == 0:
			   epoll.modify(fileno, 0)
			   connections[fileno].shutdown(socket.SHUT_RDWR)
		 elif event & select.EPOLLHUP:
			epoll.unregister(fileno)
			connections[fileno].close()
			del connections[fileno]
finally:
   epoll.unregister(serversocket.fileno())
   epoll.close()
   serversocket.close()

