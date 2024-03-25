import numpy as np
import suite2p as s2p
import matplotlib.pyplot as plt 
import ipdb
import os,glob
import pandas as pd
from multiprocessing import Pool
import seaborn as sns
from behavior import load_serial_output
sns.set_style('whitegrid')

""" To do list
Add pickling method to load and save objects easily. 
Normalize trace via z-score
High res output for heatmaps =
Have masks imported back into movie to show which neurons are called neurons. 
"""

class get_s2p():
    def __init__(self,datapath,fs=1.315235,tau=1,threshold_scaling=2,batch_size=800,blocksize=64,reg_tif=True,reg_tif_chan2=True,denoise=1):
        #Set input and output directories
        self.datapath=datapath
        self.resultpath=os.path.join(self.datapath,'figures/')
        self.resultpath_so=os.path.join(self.datapath,'figures/serialoutput/')
        self.resultpath_neur=os.path.join(self.datapath,'figures/neuronal/')

        if not os.path.exists(self.resultpath): #Make the figure directory
            os.mkdir(self.resultpath)
        if not os.path.exists(self.resultpath_so): #Make subfolder for serialoutput/behavioral data
            os.mkdir(self.resultpath_so)
        if not os.path.exists(self.resultpath_neur): #Make subfolder for neural data
            os.mkdir(self.resultpath_neur)


        #Set suite2P ops
        self.ops = s2p.default_ops()
        self.ops['batch_size'] = batch_size # we will decrease the batch_size in case low RAM on computer
        self.ops['threshold_scaling'] = threshold_scaling # we are increasing the threshold for finding ROIs to limit the number of non-cell ROIs found (sometimes useful in gcamp injections)
        self.ops['fs'] = fs # sampling rate of recording, determines binning for cell detection
        self.ops['tau'] = tau # timescale of gcamp to use for deconvolution
        self.ops['input_format']="bruker"
        self.ops['blocksize']=blocksize
        self.ops['reg_tif']=reg_tif
        self.ops['reg_tif_chan2']=reg_tif_chan2
        self.ops['denoise']=denoise

        #Set up datapath
        self.db = {'data_path': [self.datapath],}
    
    def __call__(self):
        searchstring=os.path.join(self.datapath,'**/F.npy')
        res = glob.glob(searchstring,recursive=True)
        if not res:
            self.auto_run()
            self.get_reference_image()

    def auto_run(self):
        self.output_all=s2p.run_s2p(ops=self.ops,db=self.db)

    def get_reference_image(self):
        filename=os.path.basename(self.datapath)
        filename_ref=os.path.join(self.resultpath_neur,f'{filename}referenceimage.jpg')
        filename_rigids=os.path.join(self.resultpath_neur,f'{filename}rigid.jpg')
        plt.figure(figsize=(20,20))
        plt.subplot(1, 4, 1)
        plt.imshow(self.output_all['refImg'],cmap='gray')

        plt.subplot(1, 4, 2)
        plt.imshow(self.output_all['max_proj'], cmap='gray')
        plt.title("Registered Image, Max Projection");

        plt.subplot(1, 4, 3)
        plt.imshow(self.output_all['meanImg'], cmap='gray')
        plt.title("Mean registered image")

        plt.subplot(1, 4, 4)
        plt.imshow(self.output_all['meanImgE'], cmap='gray')
        plt.title("High-pass filtered Mean registered image")
        plt.savefig(filename_ref)

class parse_s2p(get_s2p):
    def __init__(self,datapath,fs=1.315235,tau=1,threshold_scaling=2,batch_size=800,blocksize=64,reg_tif=True,reg_tif_chan2=True,denoise=1,cellthreshold=0.65):
        super().__init__(datapath,fs=1.315235,tau=1,threshold_scaling=2,batch_size=800,blocksize=64,reg_tif=True,reg_tif_chan2=True,denoise=1) #Use initialization from previous class
        self.cellthreshold=cellthreshold # Threshold to determine whether a cell is a cell. 0.7 means only the top 30% of ROIS make it to real dataset as neurons.

    def get_s2p_outputs(self):
        #Find planes and get recording/probability files
        search_path = os.path.join(self.datapath,'suite2p/plane*/')
        self.recording_files=[]
        self.probability_files=[]
        planes = [result for result in glob.glob(search_path)]
        self.recording_files.append(os.path.join(planes[0],'F.npy'))
        self.probability_files.append(os.path.join(planes[0],'iscell.npy'))

         
        if len(self.recording_files)>1 and len(self.probability_files)>1:
            #Loop over files
            self.__call__
        else:
            self.recording_file=self.recording_files[0]
            self.probability_file=self.probability_files[0]
            self.neuron_prob=np.load(self.probability_file)
            self.neuron_prob=self.neuron_prob[:,1]
            self.traces=np.load(self.recording_file)

        return
    
    def __call__(self):
        super().__call__()
        self.get_s2p_outputs()
        self.threshold_neurons()
        self.parallel_zscore()
        self.plot_all_neurons('Frames','Z-Score + i')
        self.plot_neurons('Frames','Z-Score')
        
    def threshold_neurons(self):
        self.traces=self.traces[np.where(self.neuron_prob>0.9),:] #Need to add threshold as attirbute
        self.traces=self.traces.squeeze()
        return
        
    def zscore_trace(self,trace,window_width=500):
        """ Using a sliding window, trace is zscored. 
        The sliding window is offset each iteration of the loop
        This removes any artifacts created by z score. 
        """
        ztrace=[]
        for rvalue in range(window_width):
            start=rvalue
            stop=rvalue+window_width
            zscored_trace=[]
            for i in range(round((len(trace)/(stop-start))+1)):
                if start>0 and i==0:
                    window=trace[0:start]
                    window=(window-np.mean(window))/np.std(window) #Zscrore winow
                    zscored_trace.append(window)

                if stop>len(trace):
                    window=trace[start:]
                    window=(window-np.mean(window))/np.std(window) #Zscrore winow
                    zscored_trace.append(window)
                    break

                window=trace[start:stop]
                window=(window-np.mean(window))/np.std(window) #Zscrore winow
                start+=window_width
                stop+=window_width
                zscored_trace.append(window)
            
            for i,window in enumerate(zscored_trace):
                if i==0:
                    zscored_trace=window
                else:
                    zscored_trace=np.concatenate((zscored_trace,np.asarray(window)),axis=0)
                
            ztrace.append(zscored_trace)

        ztrace=np.asarray(ztrace)
        ztrace=np.median(ztrace,axis=0)
        return ztrace
    
    def parallel_zscore(self):
        with Pool() as P:
            self.ztraces = P.map(self.zscore_trace,self.traces)

    def plot_all_neurons(self,x_label,y_label):
        # Plot neuron traces and save them without opening
        fig,ax=plt.subplots(dpi=1200)
        fig.set_figheight(100)
        fig.set_figwidth(15)
        addit=0
        for i,row in enumerate(self.ztraces):
            row+=addit
            plt.plot(row)
            addit=np.nanmax(row)

        plt.title('All Neuronal traces')
        ax.set_ylabel(x_label)
        ax.set_ylabel(y_label)

        file_string=os.path.join(self.resultpath_neur,'all_neurons.pdf')
        plt.savefig(file_string)
        plt.close()
        return

    def plot_neurons(self,x_label,y_label):   
        # Set up folder to drop traces
        self.resultpath_neur_traces = os.path.join(self.resultpath_neur,'traces')
        if not os.path.exists(self.resultpath_neur_traces):
            os.mkdir(self.resultpath_neur_traces)

        # Plot neuron traces and save them without opening
        for i,row in enumerate(self.ztraces):
            fig,ax=plt.subplots(dpi=1200)
            plt.plot(row)
            file_string=os.path.join(self.resultpath_neur,f'trace{i}.pdf')
            plt.title(file_string)
            ax.set_ylabel(x_label)
            ax.set_ylabel(y_label)
            plt.savefig(file_string)
            plt.close()

class corralative_activity(parse_s2p):
    def __init__(self,datapath,fs=1.315235,tau=1,threshold_scaling=2,batch_size=800,blocksize=64,reg_tif=True,reg_tif_chan2=True,denoise=1,cellthreshold=0.65):
        super().__init__(datapath,fs=1.315235,tau=1,threshold_scaling=2,batch_size=800,blocksize=64,reg_tif=True,reg_tif_chan2=True,denoise=1,cellthreshold=0.65)

    def get_activity_heatmap(self,data):
        plt.figure(figsize=(15,25),dpi=1200)
        plt.imshow(data,cmap='coolwarm')
        plt.ylabel('Neurons')
        plt.xlabel('Frames')
        plt.colorbar()
        plt.savefig(os.path.join(self.resultpath_neur,'general_heatmap.jpg'))

    def get_activity_correlation(self,data):
        data=data.T
        data=pd.DataFrame(data)
        correlations=data.corr(method='pearson')
        plt.figure(figsize=(15,15),dpi=1200)
        plt.matshow(correlations,cmap='inferno')
        plt.ylabel('Neuron #')
        plt.xlabel('Neuron #')
        plt.colorbar()
        plt.savefig(os.path.join(self.resultpath_neur,'correlation_analysis.jpg'))

    def general_pipeline(self):
        # Look at correlation of activity during baseline
        # Look at correlation of activity during US
        # Look at correlation of activity during post-TMT
        # Get PETHS and classify neurons by activity
        # Look at each of above correlations with respect to functional classification of neurons 

        a=1

class funcational_classification(parse_s2p):
    def __init__(self,datapath,serialoutput_object,fs=1.315235,tau=1,threshold_scaling=2,batch_size=800,blocksize=64,reg_tif=True,reg_tif_chan2=True,denoise=1,cellthreshold=0.65):
        super().__init__(datapath,fs=1.315235,tau=1,threshold_scaling=2,batch_size=800,blocksize=64,reg_tif=True,reg_tif_chan2=True,denoise=1,cellthreshold=0.65)
        self.so=serialoutput_object.behdf #Pass in serial_output_object

    def __call__(self):
        super().__call__()
        self.VanillaTS = self.parse_behavior_df('VanillaBoolean')
        self.PETH(self.ztraces,self.VanillaTS,10,[-10,-5],[0,5],'Vanilla')
        ipdb.set_trace()

    def parse_behavior_df(self,ColumnName):
        #Convert from Pandas dataframe back to numpy
        Event=self.so[ColumnName]
        ImageNumbers=self.so['ImageNumber']
        ImageNumbers=ImageNumbers.to_numpy()
        Event=Event.to_numpy()

        # Find Image number where event occurs
        ImageNumberTS=[]
        for i in range(len(Event)-1):
            if Event[i]==0 and Event[i+1]==1:
                ImageNumberTS.append(ImageNumbers[i])
        
        return ImageNumberTS

    def PETH(self,data,timestamps,window,baseline_period,event_period,event_name):
        """ PETH method will align neuronal trace data to each event of interest. 
        Inputs:
        data: float -- This is a matrix of data where each row contains dF trace data for a single neuron. Each column is a frame/time point
        timestamps: float -- This is the timestamps (taken from load_serial_output class) for trial of interest. 
        window: float default=10 -- The time (seconds) before and after each event that you would like to plot.
        baseline_period: list of two floats default=[-10,-5] -- 
        event_period: list of two floats default=[-10,-5]
        event_name: str -- This string will be used to create a subfolder in figures path. Suggest using the name of the trial type. Example: 'shocktrials'.

        Outputs:
        self.peth_stats -- Class attribute containg a list of important Area Under the Curve statistics for baseline and event. Each element corresponds to stats for a single neuron. 
        PETH graphs -> saved to the provided datapath /figures/neuronal/peths/eventname/peth_neuron{X}.jpg. If given N traces, there will be N peth graphs saved.
        """
        sampling_frequency=self.ops['fs'] # Number of Images taken per second
        window = round(window*sampling_frequency) # Convert the window (s) * the sampling frequency (Frames/s) to get number of frames in window. 

        for i,neuron_trace in enumerate(data):
            heatmap_data=[]
            BL_AUC=[] # Save the baseline AUC stats
            EV_AUC=[] # Save the Event AUC stats
            for time in timestamps:
                trace_event = neuron_trace[int(time-window):int(time+window)]
                heatmap_data.append(trace_event)

                #Calculate AUC for Baseline
                bl_trace=neuron_trace[int(time+round(baseline_period[0]*sampling_frequency)):int(time+round(baseline_period[1]*sampling_frequency))]
                BL_AUC.append(np.trapz(bl_trace))

                #Calculate AUC for Event
                ev_trace=neuron_trace[int(time+round(event_period[0]*sampling_frequency)):int(time+round(event_period[1]*sampling_frequency))]
                EV_AUC.append(np.trapz(ev_trace))

            mean_trace=np.asarray(heatmap_data).mean(axis=0) # Get Average trace across events for Neuron

            # Plot PETH
            plt.figure(figsize=(15,15),dpi=1200)
            f, axes = plt.subplots(2, 1, sharex='col')
            plt.subplot(2, 1, 1)
            axes[0] = plt.plot(mean_trace)
            ax = plt.subplot(2, 1, 2)
            axes[1].pcolor(heatmap_data)
            #ax.colarbar()
            plt.title(event_name)
            plt.savefig(os.path.join(self.resultpath_neur,f'{event_name}PETH_Neuron{i}.pdf'))
            plt.close()

        # Get Raster-PETH for each neuron's activity across conditions. (10 second before and after)
        # Plot raster-PETHS across trials 

    def classify_neuron(self):
        ipdb.set_trace()
        # Vanilla Event, Peanut Butter Event
        # Trial 1 , 2 , 3 ,4, 5, .. N, 
        # delta AUC1 (Baseline-Event), delta AUC2
    # Classify neurons into sections (Water, TMT, Vanilla, Peanut Butter)
        # Based on change in activity from baseline and fidelity?
    #
        
    def create_labeled_movie(self):
        #Take motion corrected images and overlay mask based on functional classification in python
        a=1

        
def main(serialoutput_search, twophoton_search):
    # Find and match all 2P image folders with corresponding serial output folders
    behdirs = glob.glob(serialoutput_search)
    twoPdirs = glob.glob(twophoton_search)
    final_list=[]
    for diroh in twoPdirs:
        _,cage,mouse,_=diroh.upper().split('_')
        for bdiroh in behdirs:
            _,cageb,mouseb = bdiroh.upper().split('_')
            if cage==cageb and mouse==mouseb:
                final_list.append([diroh,bdiroh])

    recordings=[]
    for imagepath,behpath in final_list:
        #Get behavior data object
        so_obj = load_serial_output(behpath)
        so_obj()

        s2p_obj = funcational_classification(imagepath,so_obj)
        s2p_obj()
        s2p_obj.get_activity_heatmap(s2p_obj.traces) #Get the heatmap for whole session
        s2p_obj.get_activity_correlation(s2p_obj.traces) #Get the correlation matrix plot for all neurons
        recordings.append(s2p_obj)

    return recordings

if __name__=='__main__':
    #Set up command line argument parser
    # parser = argparse.ArgumentParser()
    # parser.add_argument('--headless', action='store_true') #Folder containing two photon's TIFF images
    # parser.add_argument('--subject_two_photon_data',type=str,required=False) #Folder containing two photon's TIFF images
    # parser.add_argument('--serial_output_data',type=str,required=False) #Folder containing the serial outputs from the sync and sens aurduinos
    # parser.add_argument('--deep_lab_cut_data',type=str,required=False) #Folder continaing deeplabcut output data for video.
    # args=parser.parse_args()

    # # Run headless or run main function.
    # if args.headless:
    #     print('headless mode')
    # else:
    recordings=main(r'C:\Users\listo\tmtassay\TMTAssay\Day1\serialoutput\**\*24*',r'C:\Users\listo\tmtassay\TMTAssay\Day1\twophoton\**\*24*')
        # ipdb.set_trace()