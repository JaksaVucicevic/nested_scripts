#from pytriqs.lattice.tight_binding import *
from pytriqs.lattice.bz_patch import *
from pytriqs.dos.hilbert_transform import *
import pytriqs.utility.mpi as mpi

from pytriqs.plot.mpl_interface import *

import numpy as np
from numpy import pi
import numpy.linalg
from scipy.spatial import Voronoi



from data_containers import IBZ

class dca_struct:
    def __init__(self, n1,m1,n2,m2, TB):
        self.n1 = n1
        self.m1 = m1
        self.n2 = n2
        self.m2 = m2              
        
        self.TB = TB
        
        self.dim = abs(n1*m2 - m1*n2)
        if mpi.rank == 0:
            print 'dca_scheme:'
            print "   Nc = ", self.dim
            print "   n1,m1,n2,m2 = ", n1,m1,n2,m2
        
        self.eps = 0.001
        self.ex, self.ey, self.R1, self.R2, self.d1, self.d2 = self.get_auxiliary()
        self.r_points = self.get_r_points()
        self.k_unit, self.k_points = self.get_k_points()
        self.dca_patches = self.get_dca_patches()
        self.ij_to_0i = self.get_ij_to_0i_map()
        self.P, self.Pinv = self.get_FT_matrices()
        
        
    def get_auxiliary(self):
        n1, n2, m1, m2 = self.n1, self.n2, self.m1, self.m2
        
        ex = np.array([1,0])
        ey = np.array([0,1])

        R1 = n1 * ex + m1 * ey
        R2 = n2 * ex + m2 * ey

        d1 = np.array([m2,-n2])/float(n1*m2-m1*n2)
        d2 = np.array([m1,-n1])/float(m1*n2-n1*m2)

        return ex, ey, R1, R2, d1, d2

    def get_xy_minmax(self):
        R1,R2 = self.R1, self.R2
        x_min = min(0, R1[0], R2[0], (R1+R2)[0])
        x_max = max(0, R1[0], R2[0], (R1+R2)[0])
        y_min = min(0, R1[1], R2[1], (R1+R2)[1])
        y_max = max(0, R1[1], R2[1], (R1+R2)[1])
        return x_min,x_max,y_min,y_max  
        
    def get_r_points(self):
        eps = self.eps
        ex, ey, R1, R2, d1, d2 = self.ex, self.ey, self.R1, self.R2, self.d1, self.d2
        
        x_min,x_max,y_min,y_max = self.get_xy_minmax()
        # Get the direct lattice points
        r_points = []
        for x in range(x_min, x_max+1):
            for y in range(y_min, y_max+1):
                v = x * ex + y * ey
                if (np.dot(v,d1)>-eps) and (np.dot(v,d2)>-eps) and (np.dot(v,d1)<(1-eps)) and (np.dot(v,d2)<(1-eps)):
                    r_points.append(v)
        r_points = np.array(r_points)
        assert(len(r_points) == self.dim)
        return r_points

    def get_k_points(self): 
        dim, eps = self.dim, self.eps
        R1, R2, d1, d2 = self.R1, self.R2, self.d1, self.d2
        
        # The k-points are generated by 2\pi * d1,d2
        # We work in units of 2 \pi
        u_min = min(0, np.dot(np.array([1,0]), R1), np.dot(np.array([0,1]), R1), np.dot(np.array([1,1]), R1))
        u_max = max(0, np.dot(np.array([1,0]), R1), np.dot(np.array([0,1]), R1), np.dot(np.array([1,1]), R1))
        v_min = min(0, np.dot(np.array([1,0]), R2), np.dot(np.array([0,1]), R2), np.dot(np.array([1,1]), R2))
        v_max = max(0, np.dot(np.array([1,0]), R2), np.dot(np.array([0,1]), R2), np.dot(np.array([1,1]), R2))

        # Get the reciprocal lattice points
        k_unit = []
        for u in range(u_min, u_max+1):
            for v in range(v_min, v_max+1):
                kv = u * d1 + v * d2
                if (kv[0]>-eps) and (kv[1]>-eps) and (kv[0]<(1-eps)) and (kv[1]<(1-eps)):
                    k_unit.append(kv)
        pi = np.arccos(-1)
        k_unit = np.array(k_unit)
        k_points = 2*pi*k_unit
        assert(len(k_unit) == dim)
        return k_unit, k_points
    
    @classmethod
    def get_wigner_seitz(cls, k1, k2, L=10):
        kpts = []
        for u in range(-L,L):
            for v in range(-L,L):
                kpts.append(u*k1+v*k2)
        V = Voronoi(np.array(kpts))
        res = np.array([ V.vertices[n] for n in V.regions[V.point_region[2*L*L+L]] ])
        return res   
    
    def get_voronoi(self):
        k1,k2,k_unit,L = self.d1, self.d2, self.k_unit, 10        
        kpts = []
        for u in range(-L,L):
            for v in range(-L,L):
                kpts.append(u*k1+v*k2)
        return Voronoi(np.array(kpts))

    def get_dca_patches(self):
        d1,d2,k_unit,TB = self.d1, self.d2, self.k_unit, self.TB
        # Define the patches
        dca_patches = []
        ws = self.__class__.get_wigner_seitz(d1,d2)
        for i, kv in enumerate(k_unit):
            p = ws + kv
            dca_patches += [ BZPatch(name = '%02d'%i, polygons = [p]) ]
    
        # Hilbert transforms
        for p in dca_patches:
          p.ht = HilbertTransform(p.dos(TB, 101, 400))
        return dca_patches    
    
    def get_ij_to_0i_map(self):
        # Fill the map (i,j) --> (0,i)
        dim, eps, d1, d2, R1, R2, r_points = self.dim, self.eps, self.d1, self.d2, self.R1, self.R2, self.r_points
        ij_to_0i = np.zeros((dim,dim), np.int32)
        for i in range(dim):
          for j in range(dim):
            v = r_points[0] + r_points[j] - r_points[i]
            if (np.dot(v,d1)<-eps): v += R1
            if (np.dot(v,d1)>(1-eps)): v -= R1
            if (np.dot(v,d2)<-eps): v += R2
            if (np.dot(v,d2)>(1-eps)): v -= R2
            for ind, rv in enumerate(r_points):
                if (np.linalg.norm(v-rv) < eps):
                  ij_to_0i[i,j] = ind
                  break
        return ij_to_0i  

    def i_to_ij(self,ind):
        for i in range(self.dim):
            for j in range(self.dim):
                if self.ij_to_0i[i,j] == ind:
                    return i,j
        assert False, "dca i_to_ij: not found!!!!"
    
    def get_identical_pairs(self):
        dim, ij_to_0i = self.dim, self.ij_to_0i
        identical_pairs = []
        for i in range(dim):
            for j in range(dim):
                found = False
                for l,ip in enumerate(identical_pairs):                    
                    if ij_to_0i[i,j] == ij_to_0i[ip[0][0],ip[0][1]]:
                        identical_pairs[l].append([i,j])
                        found = True
                        break
                if not found:
                    identical_pairs.append([[i,j]])                    
        return identical_pairs

    def get_FT_matrices(self):
        dim, r_points, k_points = self.dim, self.r_points, self.k_points
        # Basis change matrices
        P = np.zeros([dim,dim], np.complex)
        for j in range(dim):
          for k in range(dim):
            P[j,k] = np.exp(1j * np.dot(k_points[k], r_points[j]))

        Pinv = np.linalg.inv(P)
        return P, Pinv

    def get_QK_from_QR(self, QK_iw, QR_iw):
      r0 = self.get_r0()
      QK_iw.zero()
      dim = self.dim
      P, Pinv = self.P, self.Pinv
      for i in range(dim):
        for l in range(dim):
          QK_iw["%02d"%i] += dim * Pinv[i,r0] * QR_iw["%02d"%l] * P[l,i]

    def get_QR_from_QK(self, QR_iw, QK_iw, l_list = []):
      r0 = self.get_r0()
      QR_iw.zero()
      dim = self.dim
      P, Pinv = self.P, self.Pinv
      for l in (range(dim) if l_list==[] else l_list):
        for i in range(dim):
          QR_iw["%02d"%l] += P[r0,i] * QK_iw["%02d"%i] * Pinv[i,l]

    def get_independent_r_point_groups(self):
        if not ( self.m1==0 and self.n2==0 ):
          print 'inapplicable to general clusters, returning None'
          return None
        n1,m2 = self.n1,self.m2
        
        indep_r_groups = []
        for rp in self.r_points:
            if rp[0]>n1/2 or rp[1]>m2/2 or rp[1]>rp[0]: continue
            indep_r_groups.append([])
            for l in range(n1*m2):
                p = self.r_points[l,:].copy()
                if p[0]>n1/2: p[0]=n1-p[0]
                if p[1]>m2/2: p[1]=m2-p[1]
                if p[1]>p[0]: p[0], p[1] = p[1], p[0]
                if p[0] == rp[0] and p[1] == rp[1]:
                    indep_r_groups[-1].append(l)
        return indep_r_groups    

    def symmetrize_QR(self, QR):
        irs = self.get_independent_r_point_groups()
        for ir in irs:
            tot = 0.0
            for l in ir:
                tot += QR["%.2d"%l].data[:,:,:]
            tot/=len(ir)
            for l in ir:
                QR["%.2d"%l].data[:,:,:] = tot

    def get_Qk_from_QR_embedded(self, Qkw, QR_iw, ks):
        assert self.m1==0 and self.n2==0, 'inapplicable to general clusters'
        n1,m2 = self.n1,self.m2
        r_points = self.r_points
        indep_r_groups = self.get_independent_r_point_groups()
        Qkw[:,:,:] = 0.0
        for rg in indep_r_groups:
            key = "%.2d"%rg[0]
            r = r_points[rg[0]]
            rx,ry = r[0],r[1]
            #print key, r, rx,ry
            if rx == 0 and ry == 0:
                numpy.transpose(Qkw)[:,:,:] += QR_iw[key].data[:,0,0]
                continue
            pref = lambda kx,ky: 0
            for x in ([rx,-rx] if rx!=0 else [0]):
                for y in ([ry,-ry] if ry!=0 else [0]):
                    #print x,y
                    pref = lambda kx,ky,pref=pref,x=x,y=y: pref(kx,ky) + numpy.exp(-1j*(kx*x+ky*y))
                    if rx!=ry: 
                        pref = lambda kx,ky,pref=pref,x=x,y=y: pref(kx,ky) + numpy.exp(-1j*(kx*y+ky*x))
                        #print y,x       
            for kxi, kx in enumerate(ks):
                for kyi, ky in enumerate(ks):
                    Qkw[:,kxi,kyi] += pref(kx,ky)*QR_iw[key].data[:,0,0]                    

    def get_Qk_from_QR(self, Qkw, QR_iw, ks, symmetrize = True):
        assert self.m1==0 and self.n2==0, 'inapplicable to general clusters'
        n1,m2 = self.n1,self.m2
        r_points = self.r_points
        Qkw[:,:,:] = 0.0    
        for l, r in enumerate(r_points):
            key = "%.2d"%l
            rx,ry = r[0],r[1]
            #print l, r, rx,ry        
            if rx>n1/2: rx=rx-n1
            if ry>m2/2: ry=ry-m2
            #print "after:", rx,ry                
            pref = lambda kx,ky: 0
            for sgnx in [1,-1]:
                for sgny in [1,-1]:
                    for flip in [True,False]:
                        if flip:
                            pref = lambda kx,ky, pref=pref, sgnx=sgnx, sgny=sgny: pref(kx,ky) + (numpy.exp(-1j*(sgnx*ky*rx+sgny*kx*ry)))
                        else:
                            pref = lambda kx,ky, pref=pref, sgnx=sgnx, sgny=sgny: pref(kx,ky) + (numpy.exp(-1j*(sgnx*kx*rx+sgny*ky*ry)))
            pref = lambda kx,ky, pref=pref: 0.125*pref(kx,ky)        
            for kxi, kx in enumerate(ks):
                for kyi, ky in enumerate(ks):
                    Qkw[:,kxi,kyi] += pref(kx,ky)*QR_iw[key].data[:,0,0]
        

    def QK_iw_to_QKw(self, QKw, QK_iw):           
        assert self.m1==0 and self.n2==0, 'inapplicable to general clusters'
        assert self.n1==self.m2, 'must be'
        nK = self.n1
        for l in range(self.dim):
            QKw[:,l/nK,l%nK] = QK_iw["%.2d"%l].data[:,0,0]
            
    def QKw_to_QK_iw(self, QK_iw, QKw):    
        assert self.m1==0 and self.n2==0, 'inapplicable to general clusters'
        assert self.n1==self.m2, 'must be'
        nK = self.n1
        for l in range(self.dim):
            QK_iw["%.2d"%l].data[:,0,0] = QKw[:,l/nK,l%nK]

    def Qkw_to_QK_iw(self, QK_iw, Qkw):    
        print "Qkw_to_QK_iw"
        nk = len(Qkw[0,:,0])
        assert self.m1==0 and self.n2==0, 'inapplicable to general clusters'
        assert self.n1==self.m2, 'must be'
        nK = self.n1
        assert nk % nK == 0, "has to be divisible by nK"
        D = nk/nK    
        for l in range(self.dim):  
            #print "filling K: ", l        
            QK_iw["%.2d"%l].data[:,0,0] = Qkw[:,(l/nK)*D,(l%nK)*D]

    def Qrw_to_QR_iw(self, QR_iw, Qrw):    
        assert self.m1==0 and self.n2==0, 'inapplicable to general clusters'
        n1,m2 = self.n1,self.m2
        nk = len(Qrw[0,:,0])
        for l, r in enumerate(self.r_points):
          rx,ry = r[0],r[1]
          #print "l, r, rx,ry: ",l,r,rx,ry  
          if rx>n1/2: rx=rx-n1
          if ry>m2/2: ry=ry-m2
          #print "after:", rx,ry    
          QR_iw["%.2d"%l].data[:,0,0] = Qrw[:,rx,ry]

    def get_impurity_struct(self):
        return {'x': range(self.dim)}

    def get_fermionic_struct(self):
        fermionic_struct = {}
        for l in range(self.dim): fermionic_struct["%02d"%l]=[0]
        return fermionic_struct 

    def get_r0(self):
        for r0 in range(self.dim):
            if list(self.r_points[r0]) == [0,0]: return r0
        assert found, "there has to be a zero real space vector" 
    
    def plot_r_points(self, plt):
        x_min,x_max,y_min,y_max = self.get_xy_minmax()
        r_points, R1, R2, d1, d2 = self.r_points, self.R1, self.R2, self.d1, self.d2
        
        plt.plot(x_min,y_min,'.')
        plt.plot(x_max,y_max,'D')

        plt.plot([0,R1[0]],[0,R1[1]],'x-')
        plt.plot([0,R2[0]],[0,R2[1]],'x-')
        plt.plot([0,d1[0]],[0,d1[1]],'d-')
        plt.plot([0,d2[0]],[0,d2[1]],'d-')
        plt.plot(r_points[:,0],r_points[:,1],'o')
        plt.axes().set_aspect('equal')
        plt.xlim(x_min-1,x_max+1)
        plt.ylim(y_min-1,y_max+1)
        plt.show() 

    def plot_k_points(self, plt):        
        k_points, k_unit = self.k_points, self.k_unit
        plt.plot(k_points[:,0],k_points[:,1],'o')
        plt.xlim(0,2*pi)
        plt.ylim(0,2*pi)
        plt.axes().set_aspect('equal')
        plt.show()
#        plt.plot(k_unit[:,0],k_unit[:,1],'o')
#        plt.xlim(0,1.0)
#        plt.ylim(0,1.0)
#        plt.axes().set_aspect('equal')
#        plt.show()
        
