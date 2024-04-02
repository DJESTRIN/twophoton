""" Custom S2P by David James Estrin
"""
import suite2p as s2p
import matplotlib.pyplot as plt 
import os,glob
import seaborn as sns
import ipdb
import numpy as np
import cv2
import tqdm
sns.set_style('whitegrid')

class get_s2p():
    """ get suite 2P:
    This class is meant to run suite2P without the gui. 
    """
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

class manual_classification(get_s2p):
    def get_s2p_outputs(self):
        #Find planes and get recording/probability files
        search_path = os.path.join(self.datapath,'suite2p/plane*/')
        self.recording_files=[]
        self.probability_files=[]
        self.stat_files=[]
        planes = [result for result in glob.glob(search_path)]
        self.recording_files.append(os.path.join(planes[0],'F.npy'))
        self.probability_files.append(os.path.join(planes[0],'iscell.npy'))
        self.stat_files.append(os.path.join(planes[0],'stat.npy'))

        assert (len(self.recording_files)==1 and len(self.probability_files)==1) #Make sure there is only one file.

        self.recording_file=self.recording_files[0]
        self.probability_file=self.probability_files[0]
        self.neuron_prob=np.load(self.probability_file)
        self.neuron_prob=self.neuron_prob[:,1]
        self.traces=np.load(self.recording_file)

    def threshold_neurons(self):
        self.traces=self.traces[np.where(self.neuron_prob>0.9),:] #Need to add threshold as attirbute
        self.traces=self.traces.squeeze()
        return

    def __call__(self):
        self.get_s2p_outputs()
        self.threshold_neurons()
        self.create_vids()
        self.evaluate_neurons()
    
    def scale_image(self,image,scalar):
        image=np.copy(image)
        image_new=image*scalar
        if image_new.max()>255:
            scalar=scalar-1
            image_new = self.scale_image(image,scalar)
        return image_new,scalar

    def create_vids(self):
        # Plot all neuron masks on video across frames
        self.stat=np.load(self.stat_files[0],allow_pickle=True)
        search_path = os.path.join(self.datapath,'*.tif*')
        images = glob.glob(search_path)

        # Get min and max values of all ROIs
        for i in range(len(self.stat)):
            cellx,celly=self.stat[i]['xpix'],self.stat[i]['ypix']
            if i==0:
                frx0,frx1=cellx.min()-10,cellx.max()+10
                fry0,fry1=celly.min()-10,celly.max()+10
            else: 
                if (cellx.min())<frx0:
                    frx0=cellx.min()
                if (cellx.max())>frx1:
                    frx1=cellx.min()
                if (celly.min())<fry0:
                    fry0=celly.min()
                if (celly.max())>fry1:
                    fry1=celly.min()
        fullcrop=[frx0,frx1,fry0,fry1]

        dataoh = np.copy(self.traces)
        trace_oh = dataoh[50]
        cellx,celly=self.stat[50]['xpix'],self.stat[21]['ypix']
        frx0,frx1=cellx.min()-10,cellx.max()+10
        fry0,fry1=celly.min()-10,celly.max()+10
        norm_trace_oh = (trace_oh-trace_oh.min())/(trace_oh.max()-trace_oh.min())*100

        scalar=40
        for i,image in enumerate(images):
            img = cv2.imread(image,cv2.IMREAD_GRAYSCALE)
            inith,initw=img.shape[0],img.shape[1]
            img_crop=img[fullcrop[0]:fullcrop[1],fullcrop[2]:fullcrop[3]]
            img_crop=cv2.resize(img_crop,(inith,initw))

            #Cut out the specific cell
            cut_image=img[frx0:frx1,fry0:fry1]
            cut_image=cv2.resize(cut_image,(inith,initw))

            shape=(inith*3,initw*2)
            blankimg = np.zeros(shape, np.float64)
            blankimg[-(inith*2):-(inith),initw:initw*2]=img_crop
            blankimg[-(inith*2):-(inith),:initw]=cut_image
            blankimg=blankimg/255
            blankimg,scalar=self.scale_image(blankimg,scalar)
          
            ys=norm_trace_oh[(i-299):(i+1)]+inith*2
            if ys.size==0:
                ys=norm_trace_oh[:(i+1)]+inith*2
                xs=range(i)
            else:
                xs=range(300)

            if len(xs)>1:
                for x,y in zip(xs,ys):
                    x+=10
                    blankimg[blankimg.shape[0]-int(round(y)),x]=255

            draw_x,draw_y=[],[]
            for xs,ys in zip(range(len(norm_trace_oh)),norm_trace_oh):
                draw_x.append(xs)
                draw_y.append(ys)
                
            draw_points = (np.asarray([draw_x, draw_y]).T).astype(np.int32)
            blankimg = cv2.polylines(blankimg, [draw_points], False, (255,255,255),2)
           
            #img = cv2.resize(img, (600, 600)) 
            #img = ((img-img.min())/(img.max()-img.min()))*255
           
            blankimg = np.float32(blankimg)
            colorimg = cv2.cvtColor(blankimg,cv2.COLOR_GRAY2RGB)
            
            #Add in mask data
            for xc,yc in zip(cellx,celly):
                b,g,r=colorimg[yc,xc,:]
                colorimg[yc,xc,:]=[b,g,r+10]

            colorimg=cv2.resize(colorimg,(800,800))
            cv2.imshow('image',colorimg)
            #cv2.waitKey()

            key = cv2.waitKey(1)#pauses for 3 seconds before fetching next image
            if key == 27:#if ESC is pressed, exit loop
                cv2.destroyAllWindows()
                break
        
        cv2.destroyAllWindows()


        ipdb.set_trace()
           # ipdb.set_trace()
            # for ROI in self.stat:
            #     x1,x2=ROI['xpix'].min(),ROI['xpix'].max()
            #     y1,y2=ROI['ypix'].min(),ROI['ypix'].max()
            #     cv2.rectangle(img, (x1, y1), (x2, y2), color=(255,0,0), thickness=2)
            #img = cv2.cvtColor(img,cv2.COLOR_GRAY2RGB)
            #video.write(img)

        # Seperate video based on neuron on hand and save


    def evaluate_neurons(self):
        ipdb.set_trace()

if __name__=='__main__':
    ev_obj=manual_classification(r'C:\Users\listo\tmtassay\TMTAssay\Day1\twophoton\24-3-18\24-3-18_C4620083_M3_R1-052')
    ev_obj()