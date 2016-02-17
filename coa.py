#!/usr/bin/python

import socket
import select 
import json
import time, platform 
import os, sys
import httplib
from pyrad import dictionary, packet, server

COAPORT=13000
RADIUS_CONFIG_FILE='/etc/radius_config'

# COA Error-Cause
#201    Residual Session Context Removed
#202    Invalid EAP Packet (Ignored)
#401    Unsupported Attribute
#402    Missing Attribute
#403    NAS Identification Mismatch
#404    Invalid Request
#405    Unsupported Service
#406    Unsupported Extension
#501    Administratively Prohibited
#502    Request Not Routable (Proxy)
#503    Session Context Not Found
#504    Session Context Not Removable
#505    Other Proxy Processing Error
#506    Resources Unavailable
#507    Request Initiated


class CoaServer(server.Server):

    def __init__(self, addresses=[], authport=1812, acctport=1813, hosts=None,
            dict=None):

        server.Server.__init__(self, addresses, authport, acctport, hosts, dict)
        self.sockfds = []
        self._realsockfds = []

    def _HandleCoaPacket(self, pkt):
        #server.Server._HandleAuthPacket(self, pkt)
        #pkt.secret = self.hosts[pkt.source[0]].secret

        #print "Received an coarequest"
        #print "Attributes: "
        #for attr in pkt.keys():
            #print "%s: %s" % (attr, pkt[attr])
        #print
        reply=self.CreateReplyPacket(pkt)
        url = 'http://127.0.0.1/api/radius.html?sessid='+pkt["Acct-Session-Id"][0]
        httpclient = httplib.HTTPConnection('localhost', 80, False)

        httpclient.request(method="GET", url=url)
        response = httpclient.getresponse()
	print response.status
	print response.reason
	print pkt["Acct-Session-Id"][0]
	print url

        if response.reason == 'OK':
            result = response.read()
        else:
            result = '0'

        if result == '1':
            reply['Error-Cause'] = 201
        else:
            reply['Error-Cause'] = 503

        reply.code=packet.DisconnectACK
        self.SendReplyPacket(pkt.fd, reply)

    def BindToAddress(self, coaport):
        """Add an address to listen to.
        An empty string indicated you want to listen on all addresses.

        :param addr: IP address to listen on
        :type  addr: string
        """
        sockfd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sockfd.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        #sockfd.bind((addr, 2000))
        sockfd.bind(('0.0.0.0', coaport))

        self.sockfds.append(sockfd)
        #self.acctfds.append(acctfd)

    def CreateCoaPacket(self, **args):
        #print COA_SECRET
        #return packet.Packet(dict=self.dict, secret=COA_SECRET, **args)
        return packet.Packet(dict=self.dict, secret=COA_SECRET, **args)

    def _ProcessInput(self, fd):
        """Process available data.
        If this packet should be dropped instead of processed a
        PacketError exception should be raised. The main loop will
        drop the packet and log the reason.

        This function calls either HandleAuthPacket() or
        HandleAcctPacket() depending on which socket is being
        processed.

        :param  fd: socket to read packet from
        :type   fd: socket class instance
        """
        if fd.fileno() in self._realsockfds:
            pkt = self._GrabPacket(lambda data, s=self:
                    s.CreateCoaPacket(packet=data), fd)
            self._HandleCoaPacket(pkt)


    def _PrepareSockets(self):
        """Prepare all sockets to receive packets.
        """ 
        for fd in self.sockfds:
            self._fdmap[fd.fileno()] = fd
            self._poll.register(fd.fileno(),
                select.POLLIN | select.POLLPRI | select.POLLERR)
        self._realsockfds = list(map(lambda x: x.fileno(), self.sockfds))

    def Run(self):
        """Main loop.
        This method is the main loop for a RADIUS server. It waits
        for packets to arrive via the network and calls other methods
        to process them.
        """
        self._poll = select.poll()
        self._fdmap = {}
        self._PrepareSockets()

        while 1:
            for (fd, event) in self._poll.poll():
                if event == select.POLLIN:
                    try:
                        fdo = self._fdmap[fd]
                        self._ProcessInput(fdo)
                    except server.ServerPacketError as err:
                        logger.info('Dropping packet: ' + str(err))
                    except packet.PacketError as err:
                        logger.info('Received a broken packet: ' + str(err))
                else:
                    logger.error('Unexpected event in server main loop')


#srv=CoaServer(dict=dictionary.Dictionary("/usr/local/share/freeradius/dictionary"))
#srv.hosts["127.0.0.1"]=server.RemoteHost("127.0.0.1",
                                         ##"testing123",
                                         ##"localhost")
#srv.BindToAddress(COAPORT)
#srv.Run()

def ForkFunc():

    global COA_SECRET

    rad_conf = file("/etc/radius_config")
    fd_radius = json.load(rad_conf)
    COA_SECRET = str(fd_radius['RADIUS_COA_SECRET'])
    rad_conf.close()

    srv=CoaServer(dict=dictionary.Dictionary("/usr/local/share/freeradius/dictionary"))
    ##srv.hosts["127.0.0.1"]=server.RemoteHost("127.0.0.1",
                                             ##"testing123",
                                             ##"localhost")
    srv.BindToAddress(COAPORT)
    srv.Run()

def CreateDaemon():

    try:
        if os.fork() > 0: os._exit(0)
    except OSError, error:
        print 'fork #1 failed: %d (%s)' % (error.errno, error.strerror)
        os._exit(1)    
    os.chdir('/')
    os.setsid()
    os.umask(0)
    try:
        pid = os.fork()
        if pid > 0:
            print 'Daemon PID %d' % pid
            os._exit(0)
    except OSError, error:
        print 'fork #2 failed: %d (%s)' % (error.errno, error.strerror)
        os._exit(1)

    sys.stdout.flush()
    sys.stderr.flush()
    si = file("/dev/null", 'r')
    so = file("/dev/null", 'a+')
    se = file("/dev/null", 'a+', 0)
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())

    ForkFunc() # function demo

if __name__ == '__main__': 

    if platform.system() == "Linux":
        CreateDaemon()
    else:
        os._exit(0)
