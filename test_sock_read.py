import socket

serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

serversocket.bind(('0.0.0.0', 8100))
serversocket.listen(1)

connectiontoclient, address = serversocket.accept()

request = connectiontoclient.recv(1024*1024*10)
print request
request = connectiontoclient.recv(1024*1024*10)
print request
request = connectiontoclient.recv(1024*1024*10)
print request
request = connectiontoclient.recv(1024*1024*10)
print request
connectiontoclient.close()
serversocket.close()
