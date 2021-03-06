from scipy import sparse
from scipy.sparse.linalg import eigen, svd as sparse_svd
from csc import divisi2
from csc.divisi2.ordered_set import OrderedSet
import numpy as np
import codecs

EPS = 1e-6
DOWN, UP = 1, -1

def make_diag(array):
    return sparse.dia_matrix(([array], [0]), shape=(len(array), len(array)))

class TrustNetwork(object):
    def __init__(self, output=None):
        self.nodes = OrderedSet()
        self._node_matrix = None
        self._node_conjunctions = None
        self._fast_matrix_up = None
        self._fast_matrix_down = None
        self._fast_conjunctions = None

    @staticmethod
    def load(node_file, matrix_up, matrix_down, conjunction_file):
        trust = TrustNetwork()
        nodes = divisi2.load(node_file)
        trust.nodes = OrderedSet(nodes)
        trust._fast_matrix_up = divisi2.load(matrix_up)
        trust._fast_matrix_down = divisi2.load(matrix_down)
        trust._fast_conjunctions = divisi2.load(conjunction_file)
        return trust
    
    def add_nodes(self, nodes):
        for node in nodes:
            self.nodes.add(node)

    def scan_edge(self, source, dest):
        self.nodes.add(source)
        self.nodes.add(dest)

    def make_matrices(self):
        self._node_matrix = sparse.dok_matrix((len(self.nodes), len(self.nodes)))
        self._node_conjunctions = sparse.dok_matrix((len(self.nodes), len(self.nodes)))

    def add_edge(self, source, dest, weight):
        source_idx = self.nodes.index(source)
        dest_idx = self.nodes.index(dest)
        #self._node_matrix[source_idx, dest_idx] = weight
        self._node_matrix[dest_idx, source_idx] = weight

    def add_conjunction(self, sources, dest, weight):
        dest_idx = self.nodes.index(dest)
        for i, source in enumerate(sources):
            self.add_edge(source, dest, weight)
            source_idx = self.nodes.index(source)
            self._node_conjunctions[dest_idx, source_idx] = 1.0

    def add_conjunction_piece(self, source, dest, weight):
        source_idx = self.nodes.index(source)
        dest_idx = self.nodes.index(dest)
        self._node_matrix[dest_idx, source_idx] = weight
        self._node_conjunctions[dest_idx, source_idx] = 1.0

    def make_fast_matrix(self):
        self._fast_matrix = self._node_matrix.tocsr()
        for i in xrange(self._node_matrix.shape[0]):
            self._node_matrix[0, i] += EPS
            self._node_matrix[i, 0] += EPS
        abs_matrix = np.abs(self._fast_matrix)
        rowsums = 1.0 / (EPS + (abs_matrix).sum(axis=1))
        rowsums = np.asarray(rowsums)[:,0]
        rowdiag = make_diag(rowsums)
        self._fast_matrix_down = (rowdiag * self._fast_matrix).tocsr()
        #self._fast_matrix_up = self._fast_matrix_down.T.tocsr()

        colsums = 1.0 / (EPS + (abs_matrix).sum(axis=0))
        colsums = np.asarray(colsums)[0,:]
        coldiag = make_diag(colsums)
        self._fast_matrix_up = (coldiag * self._fast_matrix.T).tocsr()

    def make_fast_conjunctions(self):
        csr_conjunctions = self._node_conjunctions.tocsr()
        n = csr_conjunctions.shape[0]
        scale_vec = np.zeros((n,))
        for row in xrange(n):
            nnz = csr_conjunctions[row].nnz
            if nnz > 0:
                scale_vec[row] = 1.0/nnz
        self._fast_conjunctions = make_diag(scale_vec) * csr_conjunctions

    def get_matrices(self):
        if self._fast_matrix_up is None:
            self.make_fast_matrix()
        return self._fast_matrix_up, self._fast_matrix_down

    def get_conjunctions(self):
        if self._fast_conjunctions is None:
            self.make_fast_conjunctions()
        return self._fast_conjunctions

    def corona(self):
        cmat = self.get_conjunctions()
        mat_up, mat_down = self.get_matrices()
        
        hub = np.ones((mat_up.shape[0],))
        authority = np.ones((mat_up.shape[0],))

        for iter in xrange(100):
            vec = authority + hub
            vec /= np.max(vec)
            root = vec * 0
            root[0] = 1.0
            conj_sums = cmat * vec
            conj_par = 1.0/(np.maximum(EPS, cmat * (1.0 / np.maximum(EPS, vec))))
            conj_factor = np.minimum(1.0, conj_par / (conj_sums+EPS))
            conj_diag = make_diag(conj_factor)
            combined = conj_diag * (mat_up + mat_down) + make_diag(np.ones(len(vec)))
            #combined = (mat_up + mat_down) * 0.5

            u, sigma, v = sparse_svd(combined, k=4)
            activation = np.dot(u, u[0])
            #w, v = eigen(combined, k=3, v0=root)
            #activation = v[:, np.argmax(w)]
            #activation = (activation / (activation[0]+EPS)).real
            print activation
            print sigma
            print conj_factor
            print
            hub += self._fast_matrix.T * conj_diag * activation
            authority += conj_diag * self._fast_matrix * activation
        hub /= np.max(hub)
        authority /= np.max(authority)
        return zip(self.nodes, hub, authority)

def output_edge(file, source, target, **data):
    line = u"%s\t%s\t%s" % (source, target, data)
    print line.encode('utf-8')
    print >> file, line.encode('utf-8')

from collections import defaultdict
def graph_from_conceptdb(output='conceptdb.graph'):
    import conceptdb
    from conceptdb.justify import Reason
    conceptdb.connect('conceptdb')
    outfile = open(output, 'w')
    
    counts = defaultdict(int)
    for reason in Reason.objects:
        reason_name = '/c/%s' % reason.id
        if reason.target == '/sentence/None': continue
        for factor in reason.factors:
            counts[factor] += 1
        counts[reason.target] += 1
    print 'counted'
    for reason in Reason.objects:
        reason_name = '/c/%s' % reason.id
        if reason.target == '/sentence/None': continue
        polar_weight = 1.0
        if reason.polarity == False: polar_weight = -0.5
        factor_counts = [counts[factor] for factor in reason.factors]
        if min(factor_counts) <= 3: continue
        if counts[reason.target] <= 3: continue
        for factor in reason.factors:
            output_edge(outfile, factor, reason_name, weight=reason.weight, dependencies=reason.factors)
        output_edge(outfile, reason_name, reason.target, weight=polar_weight)
    outfile.close()
    print "Done building the file."
    return graph_from_file(output)

def graph_from_file(filename):
    bn = TrustNetwork(output=None)
    found_conjunctions = set()
    counter = 0
    with codecs.open(filename, encoding='utf-8') as file:
        for line in file:
            print 'scan:', counter
            counter += 1
            line = line.strip()
            if line:
                source, target, prop_str = line.split('\t')
                bn.scan_edge(source, target)
    bn.make_matrices()
    total = counter
    counter = 0
    with codecs.open(filename, encoding='utf-8') as file:
        for line in file:
            print 'add edge:', counter, '/', total
            counter += 1
            line = line.strip()
            if line:
                source, target, prop_str = line.split('\t')
                props = eval(prop_str)
                weight = props['weight']
                dependencies = None
                if 'dependencies' in props and len(props['dependencies']) > 1:
                    bn.add_conjunction_piece(source, target, weight)
                else:
                    bn.add_edge(source, target, weight)
    file.close()
    
    bn.make_fast_matrix()
    bn.make_fast_conjunctions()
    divisi2.save(list(bn.nodes), filename+'.nodelist.pickle')
    divisi2.save(bn._fast_matrix_up, filename+'.up.pickle')
    divisi2.save(bn._fast_matrix_down, filename+'.down.pickle')
    divisi2.save(bn._fast_conjunctions, filename+'.conjunctions.pickle')
    
    return bn

def demo():
    bn = TrustNetwork()
    bn.add_nodes(('root', 'A', 'B', 'C', 'D', 'E', 'F', 'G'))
    bn.make_matrices()
    bn.add_edge('root', 'A', 1.0)
    bn.add_edge('root', 'B', 3.0)
    bn.add_edge('A', 'C', -1.0)
    bn.add_edge('B', 'C', 1.0)
    bn.add_conjunction(('A', 'B'), 'D', 1.0)
    bn.add_edge('A', 'E', 1.0)
    bn.add_edge('B', 'E', 1.0)
    bn.add_conjunction(('C', 'G'), 'F', 1.0)
    bn.add_edge('B', 'G', -1.0)
    bn.make_fast_matrix()
    bn.make_fast_conjunctions()
    results = bn.spreading_activation(np.ones((len(bn.nodes),)), root='root')
    print results
    return bn

def run_conceptnet(filename='conceptdb.graph'):
    bn = graph_from_file(filename)
    return bn


