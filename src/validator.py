from random import randint
from threading import Thread
# from Crypto.Signature import PKCS1_v1_5
# from data import transaction
import hashlib
import os
import ssl
import time
import errno
import socket
import binascii
import threading
import pickle

INCONN_THRESH = 128
OUTCONN_THRESH = 8
BUFF_SIZE = 2048


class Validator(object):

    def __init__(self, name=None, addr="0.0.0.0", port=4321, bind=True, cafile="~/.BlockchainPKI/rootCA.pem",
                 keyfile="~/.BlockchainPKI/rootCA.key", validators_capath="~/.BlockchainPKI/validators/"):
        '''
            Initialize a Validator object

            :param str name: The hostname
            :param str bind_addr: The ip address to bind to for serving inbound connections
            :param int bind_port: The port to bind to for serving inbound connections
            :param bool bind: Whether or not to bind to (addr, port)
            :param str cafile: The path to the CA 
            :param str keyfile: The path to the private key
            :param str validators_capath: The directory to where other Validators CAs are saved
        '''
        self.name = name or socket.getfqdn(socket.gethostname())
        self.address = addr, port
        self.bound = bind

        # Buffer to store incoming transactions
        self.mempool = []

        if bind:
            self.cafile = cafile
            self.keyfile = keyfile
            self.validators_capath = validators_capath

            # Initialize the network, both the send and receive context,
            # and load the necessary CAs
            self._init_net()
            self._load_root_ca(cafile=self.cafile,
                               keyfile=self.keyfile)
            self._load_other_ca(capath=self.validators_capath)

    def _init_net(self):
        '''
            Initializes a TCP socket for incoming traffic and binds it.

            If the connection is refused, -1 will be returned.
            If the address is already in use, a new random port will be recursively tried.
        '''
        try:
            self.net = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.net.settimeout(0.001)  # Blocking socket
            self.net.bind(self.address)  # Bind to address
            self.net.listen()  # Listen for connections
        except socket.error as e:
            if e.errno == errno.ECONNREFUSED:
                # Connection refused error
                return -1, e
            elif e.errno == errno.EADDRINUSE:
                # Address already in use, try another port
                addr, port = self.address
                new_port = randint(1500, 5000)
                print("Address %s:%d is already in use, trying port %d instead" %
                      (addr, port, new_port))
                self.address = addr, new_port
                self._init_net()  # Try to initialize the net again
        finally:
            # Context for decrypting incoming connections
            self.send_context = ssl.create_default_context()
            self.receive_context = ssl.create_default_context(
                ssl.Purpose.CLIENT_AUTH)

    def _load_root_ca(self, cafile, keyfile):
        '''
            Load a CA and private key

            :param str cafile: A path to the CA file
            :param str keyfile: A path to the private key
        '''
        assert self.receive_context != None, "Initialize the receive context before loading CAs."

        cafile = cafile.replace("~", os.environ["HOME"])
        keyfile = keyfile.replace("~", os.environ["HOME"])

        if os.path.exists(cafile) and os.path.exists(keyfile):
            self.receive_context.load_cert_chain(
                certfile=cafile, keyfile=keyfile)
        else:
            raise FileNotFoundError(
                "Either %s or %s does not exist. Please generate a CA and private key." % (cafile, keyfile))

    def _load_other_ca(self, capath=None):
        '''
            Loads a set of CAs from a directory 
            into the sending context
        '''
        assert self.send_context != None, "Initialize the send context before loading CAs."

        capath = capath.replace("~", os.environ["HOME"])

        if not os.path.exists(capath):
            print("Directory %s does not exist" % capath)
            cont = input("Would you like to create %s? (y/n)" % capath)
            if cont.strip() == 'y':
                os.mkdir(capath)
                print("Created %s" % capath)
        elif len(os.listdir(capath)) == 0:
            raise FileNotFoundError(
                "No other Validator CAs were found at %s. You will be unable to send any data without them." % capath)
        else:
            self.send_context.load_verify_locations(
                capath=capath or self.validators_capath)

    def receive(self):
        '''
            Receive thread; handles incoming transactions
        '''
        try:
            conn, addr = self.net.accept()
            # add this connection to a dictionary of incoming connections
            with self.receive_context.wrap_socket(conn, server_side=True) as secure_conn:
                data = ''
                while True:
                    data += secure_conn.recv(BUFF_SIZE)
                    if not data:
                        # Deserialize the entire object when data reception has ended
                        decoded_transaction = pickle.loads(data)
                        print("Received data from %s:%d: %s" %
                              (addr[0], addr[1], decoded_transaction))
                        # check if this transaction is in mempool
                        # broadcast to network
                        return decoded_transaction
        except socket.timeout:
            pass

    def message(self, v, msg):
        '''
            Send a message to another Validator

            :param Validator v: receiver of the message
            :param msg: the message to send

            v's net should be initialized and listening for incoming connections,
            probably bound to listen for all connections (addr="0.0.0.0").
            msg must be an instance of str or bytes.
        '''
        if self.net and self != v:
            # Connect to v's inbound net using self's outbound net
            address = v.address
            if not isinstance(msg, str):
                raise TypeError(
                    "msg should be of type str, not %s" % type(msg))
            else:
                if isinstance(msg, str):
                    msg = msg.encode()  # encode the msg to binary
                print("Attempting to send to %s:%s" % v.address)
                secure_conn = self.send_context.wrap_socket(socket.socket(
                    socket.AF_INET, socket.SOCK_STREAM), server_hostname=v.name)
                secure_conn.settimeout(0.001)
                try:
                    secure_conn.connect(address)  # Connect to v
                    # Send the entirety of the message
                    secure_conn.sendall(msg)
                except OSError as e:
                    # Except cases for if the send fails
                    if e.errno == errno.ECONNREFUSED:
                        print(e)
                        # return -1, e
                except socket.error as e:
                    print(e)
                finally:
                    # secure_conn.shutdown(socket.SHUT_RDWR)
                    secure_conn.close()
        else:
            raise Exception(
                "The net must be initialized and listening for connections")

    def close(self):
        '''
            Closes a Validator and its net
        '''
        if self.bound and self.net != None:
            # Close socket
            self.net.close()


    # Get the merkel root from the block.
    # Recalculate the merkel root from the pool. When the Block Generator is chosen
    # from Round Robin Algorithm, he/she will send the update to all of the validator
    # nodes. The update will contain the first and last position of the proposed 
    # transactions (transactions inside a new block in propose status) inside the pool 
    # 
    # Use the position to pull the transactions from the local pool and recalculate the
    # merkel root. Compare the new block's merkel root with recalculated merkel root. If they
    # are the same then send YES.
    def verify_txs_from_merkel_root(self, merkel_root, first, last):
        transactions = []
        for i in range(first, last+1):
            transactions.append(self.mempool[i])

        sha256_txs = self.hash_tx(transactions)
        calculated_merkle_root = self.compute_merkle_root(sha256_txs)
        
        if calculated_merkle_root == merkel_root:
            print("Send to the other validators YES")
        else:
            print("Send to the other validators NO")
    

    # Return a list of hashed transactions
    def hash_tx(self, transaction):
        sha256_txs = []
        # A hash of the root of the Merkel tree of this block's transactions.
        for tx in transaction:
            tx_hash = tx.compute_hash()
            sha256_txs.append(tx_hash)

        return sha256_txs


    # Return the root of the hash tree of all the transactions in the block's transaction pool (Recursive Function)
    # Assuming each transaction in the transaction pool was HASHed in the Validator class (Ex: encode with binascii.hexlify(b'Blaah'))
    # The number of the transactions hashes in the pool has to be even. 
    # If the number is odd, then hash the last item of the list twice
    def compute_merkle_root(self, transactions):
        # If the length of the list is 1 then return the final hash
        if len(transactions) == 1:
            return transactions[0]

        new_tx_hashes = []

        for tx_id in range(0, len(transactions)-1, 2):  # for(t_id = 0, t_id < len(transactions) - 1, t_id = t_id + 2)
            
            tx_hash = self.hash_2_txs(transactions[tx_id], transactions[tx_id+1])
            new_tx_hashes.append(tx_hash)

        # if the number of transactions is odd then hash the last item twice
        if len(transactions % 2 == 1):
            tx_hash = self.hash_2_txs(transactions[-1], transactions[-1])
            new_tx_hashes.append(tx_hash)

        return self.compute_merkle_root(new_tx_hashes)

    # Hash two hashes together -> return 1 final hash
    def hash_2_txs(self, hash1, hash2):
        # Reverse inputs before and after hashing because of the big-edian and little-endian problem
        h1 = hash1.hexdigest()[::-1]
        h2 = hash2.hexdigest()[::-1]
        hash_return = hashlib.sha256((h1+h2).encode())

        return hash_return.hexdigest()[::-1]


if __name__ == "__main__":
    Alice = Validator(port=1234, cafile="/mnt/c/Users/owner/Documents/University of Memphis/Capstone Project/workspace/blockchainPKI/rootCA.pem",
    keyfile="/mnt/c/Users/owner/Documents/University of Memphis/Capstone Project/workspace/blockchainPKI/rootCA.key")
    Bob = Validator(name="Bob", addr="10.102.15.201", port=1234, bind=False)
    Marshal = Validator(name="marshal-mbp.memphis.edu",
                       addr="10.101.70.197", port=7123, bind=False)
    Brandon = Validator(name="brandonsmacbook.memphis.edu",
                       addr="10.102.114.244", bind=False)

    try:
        while True:
            # Receives incoming transactions
            #Alice.message(Marshal, "Hello, Marshal. This is Dung Le.")
            Alice.receive()
            time.sleep(0.5)
    except KeyboardInterrupt:
        Alice.close()
        Bob.close()
