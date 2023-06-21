import Pyro5.api
import base64
from itertools import cycle
from collections import defaultdict
from random import choice
from .base import RedundantStorageScheme
from ...striping import stripe_blocks
from ...block import make_block
from ...metadata import make_metadata
from ...networking import peers_available_to_host, hosting_peers, block_name_for_file
from ...file import write_file


class NaiveDuplication(RedundantStorageScheme):
    """
    This scheme adds redundancy to increase the availability of the file by
    simply duplicating the file across N peers. It differs from the "hosting"
    scheme in that it stores the file on N peers instead of just one.

    To store the file, we discover live peers, select N of them, and store a
    copy of the file on each of them ("stripe" the copies across the peers).
    To retrieve the file, we discover all hosting peers and download the file
    from one (any) of them.
    """

    _N = None

    def __init__(self, number_of_peers):
        self.number_of_peers = number_of_peers

    @property
    def number_of_peers(self):
        return self._N

    @number_of_peers.setter
    def number_of_peers(self, N):
        self._N = N

    def introduce_redundancy(self, blocks):
        """ Add redundancy to the blocks to facilitate error recovery. """
        # just repeat the block N times, where N
        # is the number of peers
        # we expect there to be exactly one block
        # with this scheme
        block = blocks[0]
        return [block for i in range(self.number_of_peers)]

    def allocate(self, blocks, host_uids) -> dict:
        """ Allocate all blocks to the available hosts."""
        # TODO: move to base class, probably
        allocations = defaultdict(list)
        # round robin allocation
        for h in cycle(host_uids):
            if not blocks:
                break
            allocations[h].append(blocks.pop())
        return allocations

    def store(self, file):
        """ The main entry point to store a file using this scheme. """
        block = make_block(file.data)
        metadata = make_metadata(block, file.name)
        peer_uids = peers_available_to_host(metadata)
        blocks = [block]
        blocks = self.introduce_redundancy(blocks)
        peer_allocation = self.allocate(blocks, peer_uids)
        for peer_uid in peer_allocation:
            peer_blocks = peer_allocation[peer_uid]  # list of blocks
            stripe_blocks(peer_uid, peer_blocks)
        # TODO: store filename: root_block_checksum on FS
        # TODO: store block checksum: [block_checksum]-or-peer_uid/name
        # try to implement the block tree and file dir
        # in a short feedback loop - in REPL for instance
        # note two files with different names but the same contents would reuse

    def get(self, filename):
        """ The main entry point to get a file that was stored using this
        scheme. """
        block_name = block_name_for_file(filename)
        peers = hosting_peers(block_name)
        # TODO: when peer metadata is added, we can select the
        # "best" peer here instead of a random peer
        chosen_peer = choice(peers)
        with Pyro5.api.Proxy(chosen_peer) as peer:
            # TODO: need to also retrieve the metadata
            # to compare the checksum
            file_contents = peer.retrieve(block_name)
            decoded = base64.decodebytes(bytes(file_contents['data'], 'utf-8'))
            # write it with the original filename
            # instead of the block name
            write_file(filename, decoded)
