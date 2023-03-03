import numpy as np
from hmm_utils import forward_algorithm
from hmm_utils import backward_algorithm
from hmm_utils import proposal_density
from scipy.special import logsumexp
from scipy.optimize import minimize
import argparse
import os

def parse_args():
	parser = argparse.ArgumentParser()
	parser.add_argument('--times',type=str, default=None)
	parser.add_argument('--popFreq',type=float,default=None)

	parser.add_argument('--ancientSamps',type=str,default=None)
	parser.add_argument('--out',type=str,default=None)

	parser.add_argument('-N','--N',type=float,default=10**4)
	parser.add_argument('-coal','--coal',type=str,default=None,help='path to Relate .coal file. Negates --N option.')

	parser.add_argument('--tCutoff',type=float,default=1000)
	parser.add_argument('--timeBins',type=str,default=None)
	parser.add_argument('--sMax',type=float,default=0.1)
	parser.add_argument('--df',type=int,default=400)
	return parser.parse_args()

def load_times(readtimes): # these are time on an absolute scale, everything else is ones
	file1 = open(readtimes, 'r')
	Lines = file1.readlines()
	der = Lines[0].split(",")
	anc = Lines[1].split(",")
	ancnum = [-1] * (len(anc) - 1)
	dernum = [-1] * (len(der) - 1)
	for i in range(len(der) - 1):
		dernum[i] = float(der[i])
	for i in range(len(anc) - 1):
		ancnum[i] = float(anc[i])
	
	print(dernum)
	print(ancnum)
	locusDerTimes = np.empty((len(dernum), 1)) # no thinning or burn-in
	locusAncTimes =  np.empty((len(ancnum), 1))
	M = locusDerTimes.shape[1]
	ntot = locusDerTimes.shape[0] + locusAncTimes.shape[0] + 2 # why not just completely fill it out???
	locusDerTimes[:,0] = dernum
	locusAncTimes[:,0] = ancnum

	row0 = -1.0 * np.ones((ntot,M))

	row0[:locusDerTimes.shape[0],:] = locusDerTimes

	row1 = -1.0 * np.ones((ntot,M))

	row1[:locusAncTimes.shape[0],:] = locusAncTimes
	locusTimes = np.array([row0,row1])
	#locus time is an array that has dimensions 2 by (total number of leaves) by (number of importance samples)
	#The first row corresponds to the derived alleles. The columns are populated by daf-1 and n-daf-1 entries each, and are then -1 below this value.
	return locusTimes

def load_data(args):
		# load coalescence times
	noCoals = (args.times == None)
	if not noCoals:
		times = load_times(args.times)
	else:
		times = np.zeros((2,0,0))
	currFreq = args.popFreq

	# load ancient samples/genotype likelihoods
	if args.ancientSamps != None:
		ancientGLs = np.genfromtxt(args.ancientSamps,delimiter=' ')
	else:
		ancientGLs = np.zeros((0,4))

	# load ancient haploid genotype likelihoods
	ancientHapGLs = np.zeros((0,3))

	if noCoals:
		try:
			tCutoff = np.max(ancientGLs[:,0])+1.0
		except:
			tCutoff = np.max(ancientHapGLs[:,0])+1.0
	else:
		tCutoff = args.tCutoff

	epochs = np.arange(0.0,tCutoff,int(1))
	# loading population size trajectory
	if args.coal != None:
		Nepochs = np.genfromtxt(args.coal,skip_header=1,skip_footer=1)
		N = 0.5/np.genfromtxt(args.coal,skip_header=2)[2:-1]
		N = np.array(list(N)+[N[-1]])
		Ne = N[np.digitize(epochs,Nepochs)-1]
	else:
		Ne = args.N * np.ones(int(tCutoff))
	# set up freq bins
	c = 1/(2*np.min([Ne[0],100000]))
	df = args.df
	freqs = np.linspace(c,1-c,df)
	# load time bins (for defining selection epochs)
	if args.timeBins != None:
		timeBins = np.genfromtxt(args.timeBins)
	else:
		timeBins = np.array([0.0,tCutoff])

	return timeBins,times,epochs,Ne,freqs,ancientGLs,ancientHapGLs,noCoals,currFreq

def likelihood_wrapper(theta,timeBins,N,freqs,z_bins,z_logcdf,z_logsf,ancGLs,ancHapGLs,gens,noCoals,currFreq,sMax):
	S = theta
	Sprime = np.concatenate((S,[0.0]))
	if np.any(np.abs(Sprime) > sMax):
		return np.inf
	sel = Sprime[np.digitize(epochs,timeBins,right=False)-1]
	tShape = times.shape
	if tShape[2] == 0:
		t = np.zeros((2,0))
		importanceSampling = False
	elif tShape[2] == 1:
		t = times[:,:,0]
		importanceSampling = False
	else:
		importanceSampling = True
	if importanceSampling:
		M = tShape[2]
		loglrs = np.zeros(M)
		for i in range(M):
			betaMat = backward_algorithm(sel,times[:,:,i],epochs,N,freqs,z_bins,z_logcdf,z_logsf,ancGLs,ancHapGLs,noCoals=noCoals,currFreq=currFreq)
			logl = logsumexp(betaMat[-2,:])
			logl0 = proposal_density(times[:,:,i],epochs,N)
			loglrs[i] = logl-logl0
		logl = -1 * (-np.log(M) + logsumexp(loglrs))
	else:
		betaMat = backward_algorithm(sel,t,epochs,N,freqs,z_bins,z_logcdf,z_logsf,ancGLs,ancHapGLs,noCoals=noCoals,currFreq=currFreq)
		logl = -logsumexp(betaMat[-2,:])
	return logl

def traj_wrapper(theta,timeBins,N,freqs,z_bins,z_logcdf,z_logsf,ancGLs,ancHapGLs,gens,noCoals,currFreq,sMax):
	S = theta
	Sprime = np.concatenate((S,[0.0]))
	if np.any(np.abs(Sprime) > sMax):
		print('WARNING: selection coefficient exceeds bounds. Maybe change --sMax?')
		return np.inf

	sel = Sprime[np.digitize(epochs,timeBins,right=False)-1]
	T = len(epochs)
	F = len(freqs)
	tShape = times.shape
	if tShape[2] == 0:
		t = np.zeros((2,0))
		importanceSampling = False
	elif tShape[2] == 1:
		t = times[:,:,0]
		importanceSampling = False
	else:
		importanceSampling = True

	if importanceSampling:
		M = tShape[2]
		loglrs = np.zeros(M)
		postBySamples = np.zeros((F,T-1,M))
		for i in range(M):
			betaMat = backward_algorithm(sel,times[:,:,i],epochs,N,freqs,z_bins,z_logcdf,z_logsf,ancGLs,ancHapGLs,np.array([]),noCoals=noCoals,currFreq=currFreq)
			alphaMat = forward_algorithm(sel,times[:,:,i],epochs,N,freqs,z_bins,z_logcdf,z_logsf,ancGLs,ancHapGLs,noCoals=noCoals)
			logl = logsumexp(betaMat[-2,:])
			logl0 = proposal_density(times[:,:,i],epochs,N)
			loglrs[i] = logl-logl0
			postBySamples[:,:,i] = (alphaMat[1:,:] + betaMat[:-1,:]).transpose()
		post = logsumexp(loglrs + postBySamples,axis=2)
		post -= logsumexp(post,axis=0)

	else:
		post = np.zeros((F,T))
		betaMat = backward_algorithm(sel,t,epochs,N,freqs,z_bins,z_logcdf,z_logsf,ancGLs,ancHapGLs,noCoals=noCoals,currFreq=currFreq)
		alphaMat = forward_algorithm(sel,t,epochs,N,freqs,z_bins,z_logcdf,z_logsf,ancGLs,ancHapGLs,noCoals=noCoals)
		post = (alphaMat[1:,:] + betaMat[:-1,:]).transpose()
		post -= logsumexp(post,axis=0)
	return post

if __name__ == "__main__":
	args = parse_args()
	if args.times == None and args.ancientSamps == None:
		print('You need to supply coalescence times (--times) and/or ancient samples (--ancientSamps)')
	
	# load data and set up model
	sMax = args.sMax	
	timeBins,times,epochs,Ne,freqs,ancientGLs,ancientHapGLs,noCoals,currFreq = load_data(args)
	# read in global Phi(z) lookups
	z_bins = np.genfromtxt(os.path.dirname(__file__) + '/utils/z_bins.txt')
	z_logcdf = np.genfromtxt(os.path.dirname(__file__) + '/utils/z_logcdf.txt')
	z_logsf = np.genfromtxt(os.path.dirname(__file__) + '/utils/z_logsf.txt')

	Ne *= 1/2
	noCoals = int(noCoals)

	# optimize over selection parameters
	T = len(timeBins)
	S0 = 0.0 * np.ones(T-1)
	opts = {'xatol':1e-4}

	if T == 2:
		Simplex = np.reshape(np.array([-0.05,0.05]),(2,1))
	elif T > 2:
		Simplex = np.zeros((T,T-1))
		for i in range(Simplex.shape[1]):
			Simplex[i,:] = -0.01
			Simplex[i,i] = 0.01
		Simplex[-1,:] = 0.01
	else:
		raise ValueError

	opts['initial_simplex']=Simplex
	    
	logL0 = likelihood_wrapper(S0,timeBins,Ne,freqs,z_bins,z_logcdf,z_logsf,ancientGLs,ancientHapGLs,epochs,noCoals,currFreq,sMax)

	if times.shape[2] > 1:
		print('\t(Importance sampling with M = %d Relate samples)'%(times.shape[2]))
		print()
	minargs = (timeBins,Ne,freqs,z_bins,z_logcdf,z_logsf,ancientGLs,ancientHapGLs,epochs,noCoals,currFreq,sMax)
	res = minimize(likelihood_wrapper, S0, args=minargs, options=opts, method='Nelder-Mead')

	S = res.x
	L = res.fun

	toprint = []

	toprint.append('logLR: %.4f'%(-res.fun+logL0) + "\n")
	toprint.append('Epoch\tSelection MLE'+ "\n")
	for s,t,u in zip(S,timeBins[:-1],timeBins[1:]):
		toprint.append('%d-%d\t%.5f'%(t,u,s)+ "\n")

	# infer trajectory @ MLE of selection parameter
	post = traj_wrapper(res.x,timeBins,Ne,freqs,z_bins,z_logcdf,z_logsf,ancientGLs,ancientHapGLs,epochs,noCoals,currFreq,sMax)
	
	f = open(args.out+"_inference.txt", "w+")
	f.writelines(toprint)
	f.close()
	np.savetxt(args.out+"_post.txt", post, delimiter=",") #print(i,np.sum(freqs * np.exp(post[:,i])))
	np.savetxt(args.out+"_freqs.txt", freqs, delimiter=",") #print(i,np.sum(freqs * np.exp(post[:,i])))
