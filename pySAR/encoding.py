################################################################################
#################                    Encoding                  #################
################################################################################

import pandas as pd
import numpy as np
import time
import itertools
import sys
from tqdm.auto import tqdm
from difflib import get_close_matches
import json

from aaindex import aaindex1
from .model import Model
from .pyDSP import PyDSP
from .evaluate import Evaluate
from .pySAR import PySAR
from .utils import *
from .descriptors import Descriptors

class Encoding(PySAR):
    """
    The use-case of this class is when you have a dataset of protein sequences with
    a sought-after protein activity/fitness value and you want to measure this activity
    value for new and unseen sequences that have not had their activity value
    experimentally measured. The encoding class allows for evaluation of a variety
    of potential techniques at which to numerically encode the protein sequences,
    allowing for the builiding of predictive regression ML models that can ultimately
    predict the activity value of an unseen protein sequence. The strategies each
    generate a huge number of potential models that you can then assess for performance
    and predictability, selecting the best-performing model out of all those evaluated.

    The encoding class inherits from the main PySAR module and allows for a
    dataset of protein sequences to be encoded through 3 main strategies: AAI Indices,
    protein Descriptors and AAI Indices + protein Descriptors. The encoding class
    and its methods differ from the PySAR class by allowing for the encoding using
    all available features. To date, there are 566 indices supported in the AAI and
    pySAR supports 15 different descriptors. The features can be encoeed using
    different combinations, for example, 1, 2 or 3 descriptors can be used for the
    descriptor and AAI + Descriptor encoding strategies. In total, this class
    supports over 410,000 possible ways at which to numerically encode the
    protein sequences in the building of a predictive ML model for mapping these
    sequences to a particular activity, known as a Sequence-Activity-Relationship (SAR).

    Parameters
    ----------
    :config_file (str): 
        path to configuration file with all required parameters for the pySAR encoding
        pipeline.

    Methods
    -------
    aai_encoding(aai_list=None, cutoff_index=1):
        encoding protein sequences using indices from the AAI.
    descriptor_encoding(desc_combo=1):
        encoding protein sequences using protein descriptors from descriptors module.
    aai_descriptor_encoding(desc_combo=1, use_dsp=True):
        encoding protein sequences using indices from the AAI in concatenation
        with the protein descriptors from the descriptors module.
    """
    def __init__(self, config_file=""):

        self.config_file = config_file
        #pass config file into parent pySAR class
        super().__init__(self.config_file)
        
        #setting DSP params to None if not using them
        if not (self.use_dsp):
            self.spectrum = None
            self.window_type = None
            self.filter_type = None

        #create output directory to store all of the program's outputs
        create_output_dir()

    def aai_encoding(self, aai_list=None, cutoff_index=1, sort_by='R2'):
        """
        Encoding all protein sequences using each of the available indices in the
        AAI. The protein spectra of the AAI indices will be generated if use_dsp is true,
        dictated by the instance attributes: spectrum, window and filter. 
        If not true then the encoced sequences from the AAI will be used. Each encoding will be
        used as the feature data to build the predictive regression models. To date,
        there are 566 indices in the AAI, therefore 566 total models can be built using
        this encoding strategy. The metrics evaluated from the model for each AAI
        encoding combination will be collated into a dataframe, saved and returned, with the 
        results sorted by R2 by default, this can be changed using the sort_by parameter. 

        Parameters
        ----------
        :aai_list : list (default=None)
            list of aai indices to use for encoding the predictive models, by default
            ALL AAI indices will be used.
        :cutoff_index : int (default=1)
            set the proportion of iterations of AAI indices to actually encode. This is mainly used for 
            testing and the default of 1 means that all indices will be used as standard.
        :sort_by : str (default=R2)
            sort output dataframe by specified column/metric value, results sorted by R2 score by default.

        Returns
        -------
        :aaindex_metrics_df : pd.DataFrame
            dataframe of calculated metric values from generated predictive models
            encoded using indices in the AAI for the AAI encoding strategy. Output will 
            be of the shape 566 x 8, where 566 is the number of indices that can be used
            for the encoding and 8 is the results/metric columns.
        """
        #initialise dataframe to store all output results of AAI encoding
        aaindex_metrics_df = pd.DataFrame(columns=['Index', 'Category', 'R2', 'RMSE',
            'MSE', 'MAE', 'RPD', 'Explained Variance'])

        #lists to store results for each predictive model
        index_ = []
        category_ = []
        r2_ = []
        mse_ = []
        rmse_ = []
        rpd_ = []
        mae_ = []
        explained_var_ = []
        # index_count = 1        #counters to keep track of current index

        #if no indices passed into aai_list then use all indices by default
        if (aai_list == None or aai_list == [] or aai_list == ""):
            all_indices = aaindex1.record_codes()
        elif (isinstance(aai_list, str)):   #if single descriptor input, cast to list
            all_indices = [aai_list]
        elif ((not isinstance(aai_list, list)) and (not isinstance(aai_list, str))):
            raise TypeError("Input AAI list is not of type list or str, got {}.".format(isinstance(aai_list, list)))
        else:
            all_indices = aai_list

        print('\n#######################################################################################\n')
        print('Encoding using {} AAI combination(s) with the parameters:\n\n# Algorithm -> {}\n# Parameters -> {} \
            \n# Test Split -> {}'.format(len(all_indices), repr(self.model), self.model.model.get_params(), self.test_split))
        if (self.use_dsp):
            print('# Using DSP -> {}\n# Spectrum -> {}\n# Window Function -> {}\n# Filter -> {}\n'.format(
                self.use_dsp, self.spectrum, self.window_type, self.filter_type
            ))
        print('\n#######################################################################################\n')

        #set the proportion of iterations to actually complete -> mainly used for testing
        cutoff_index = int(len(all_indices) * cutoff_index)

        '''
        1.) Get AAI index encoding of protein sequences, if using DSP (use_dsp = True),
        create instance of pyDSP class and generate protein spectra from the AAI
        indices, according to instance parameters: spectrum, window and filter.
        2.) Build model using encoded AAI indices or protein spectra as features.
        3.) Predict and evaluate the model using the test data.
        4.) Append index and calculated metrics to lists.
        5.) Repeat steps 1 - 4 for all indices.
        6.) Output results into a final dataframe, save it and return.
        '''

        start = time.time() #start time counter

        #using tqdm package to create a progress bar showing encoding progress,
        #   file=sys.stdout to stop error where iterations were printing out of order
        for index in tqdm(all_indices[:cutoff_index], unit=" indices", position=0, 
            desc="AAI Indices", file=sys.stdout):

            #get AAI indices encoding for sequences according to index var
            encoded_seqs = self.get_aai_encoding(index)

            #generate protein spectra from pyDSP class if use_dsp is true
            if (self.use_dsp):
                pyDSP = PyDSP(self.config_file, protein_seqs=encoded_seqs)
                pyDSP.encode_seqs()
                X = pd.DataFrame(pyDSP.spectrum_encoding)
            else:
                X = pd.DataFrame(encoded_seqs)

            #get observed activity values from the dataset
            Y = self.activity

            #split feature data and labels into train and test data
            X_train, X_test, Y_train, Y_test  = self.model.train_test_split(X, Y)

            #fit model to training data
            model_fit = self.model.fit()

            #predict activity values for the test data
            Y_pred = self.model.predict()

            #initilaise instance of Evaluate class
            eval = Evaluate(Y_test, Y_pred)

            #append values/results from current AAI encoding iteration to lists
            index_.append(index)
            category_.append(aaindex1[index].category)
            r2_.append(eval.r2)
            rmse_.append(eval.rmse)
            mse_.append(eval.mse)
            rpd_.append(eval.rpd)
            mae_.append(eval.mae)
            explained_var_.append(eval.explained_var)

        #stop time counter, work out elapsed time
        end = time.time()      
        elapsed = end - start

        print('\n\n##############################################################')
        print('Elapsed Time for AAI Encoding: {0:.3f} seconds.'.format(elapsed))

        #set columns in the output dataframe to each of the values/metrics lists
        aaindex_metrics_= aaindex_metrics_df.copy()
        aaindex_metrics_['Index'] = index_
        aaindex_metrics_['Category'] = category_
        aaindex_metrics_['R2'] = r2_
        aaindex_metrics_['RMSE'] = rmse_
        aaindex_metrics_['MSE'] = mse_
        aaindex_metrics_['RPD'] = rpd_
        aaindex_metrics_['MAE'] = mae_
        aaindex_metrics_['Explained Variance'] = explained_var_

        #convert index and category from Object -> String datatypes
        aaindex_metrics_['Index'] = aaindex_metrics_['Index'].astype(pd.StringDtype())
        aaindex_metrics_['Category'] = aaindex_metrics_['Category'].astype(pd.StringDtype())

        #sort output dataframe by sort_by parameter, sorted by R2 by default
        if (sort_by not in aaindex_metrics_df.columns):
            sort_by = 'R2'

        #sort ascending or descending depending on sort by metric
        sort_ascending = False
        if not (sort_by == "R2" or sort_by == "Explained Variance"):
            sort_ascending = True

        #sort results according to sort_by parameter (R2 by default)
        aaindex_metrics_ = aaindex_metrics_.sort_values(by=[sort_by], ascending=sort_ascending)

        #save results dataframe, saved to OUTPUT_DIR by default.
        save_results(aaindex_metrics_, 'aaindex_results')

        return aaindex_metrics_

    def descriptor_encoding(self, desc_list=None, desc_combo=1, cutoff_index=1, sort_by='R2'):
        """
        Encoding all protein sequences using the available physiochemical
        and structural descriptors from the custom-built protpy package. The sequences 
        can be encoded using combinations of 1, 2 or 3 of these descriptors, dictated 
        by the desc_combo input parameter: set this to 1, 2 or 3 for what encoding 
        combination to use, default is 1. Each descriptor encoding will be used as the 
        feature data to build the predictive regression models. With 15 descriptors 
        supported by pySAR & protpy this means there can be 15, 105 and 455 total 
        predictive models built for 1, 2 or 3 descriptors, respecitvely. These totals 
        may vary depending on the meta-parameters on some of the descriptors. The 
        metrics evaluated from the model for each descriptor encoding combination will 
        be collated into a dataframe and saved and returned, with the results sorted 
        by the R2 score, this can be changed using the sort_by parameter.

        Parameters
        ----------
        :desc_combo : int (default=1)
            combination of descriptors to use.
        :decs_list : list (default=None)
            list of descriptors to use for encoding, by default all available descriptors
            in the descriptors module will be used for the encoding.
        :cutoff_index : int (default=1)
            set the proportion of iterations of descriptors to actually encode. This is 
            mainly used for testing and the default of 1 means that all descriptors will 
            be used as standard.
        :sort_by : str (default=R2)
            sort output dataframe by specified column/metric value, results sorted by R2 
            score by default.

        Returns
        -------
        :desc_metrics_df_ : pd.DataFrame
            dataframe of calculated metric values from generated predictive models
            encoded using all or selected descriptors for the descriptors encoding strategy.
            Output will be of the shape 15 x 8, where 15 is the number of descriptors that 
            can be used for the encoding and 8 is the results/metric columns.
        """
        #create dataframe to store output results from models
        desc_metrics_df = pd.DataFrame(columns=['Descriptor', 'Group', 'R2', 'RMSE',
            'MSE', 'MAE', 'RPD', 'Explained Variance'])

        #lists to store results for each predictive model
        descriptor = []
        descriptor_group_ = []
        r2_ = []
        mse_ = []
        rmse_ = []
        rpd_ = []
        mae_ = []
        explained_var_ = []
        # desc_count = 1  #counters to keep track of current index & descriptor

        #create instance of descriptors class
        desc = Descriptors(self.config_file)

        #if no descriptors passed into desc_list then use all descriptors by default,
        #   get list of all descriptors according to desc_combo value
        if (desc_list == None or desc_list == [] or desc_list == "" ):
            all_descriptors = desc.all_descriptors_list(desc_combo)
        elif (isinstance(desc_list,str)):     #if single descriptor input, cast to list
            all_descriptors = [desc_list]
        elif ((not isinstance(desc_list, list)) and (not isinstance(desc_list, str))):
            raise TypeError("Input Descriptor list is not of type list or str, got {}.".format(isinstance(desc_list, list)))
        else:
            # desc = Descriptors(self.config_file)
            if (desc_combo == 2):
                all_descriptors = list(itertools.combinations(desc_list, 2))
            elif (desc_combo == 3):
                all_descriptors = list(itertools.combinations(desc_list, 3))
            else:
                all_descriptors = desc_list     #using default combination of descriptors

        #pretty print json config parameters
        pretty_parameters = json.dumps(self.parameters, sort_keys=True, indent=1)

        print('\n\n################################################################\n')
        print('Encoding using {} descriptor combination(s) with the parameters:\n {}\n'.format(
            len(all_descriptors), pretty_parameters))
        print('##################################################################\n')

        #set the proportion of iterations to actually complete -> mainly used for testing
        cutoff_index = int(len(all_descriptors) * cutoff_index)

        start = time.time()     #start counter

        '''
        1.) Get current descriptor value or combination of descriptors from all_descriptors list.
        2.) Build model using descriptor features from current descriptor(s).
        3.) Predict and evaluate the model using the test data.
        4.) Append descriptor(s) and calculated metrics to lists.
        5.) Repeat steps 1 - 4 for all descriptors.
        6.) Output results into a final dataframe, save it and return, sorting by sort_by parameter.
        '''

        for descr in tqdm(all_descriptors[:cutoff_index], unit=" descriptor", position=0, 
            desc="Descriptors", file=sys.stdout):

            #reset descriptor DF and list
            desc_ = pd.DataFrame()           
            descriptor_list = []

            #counter to keep track of current descriptor
            # desc_count+=1          

            #if using 2 or 3 descriptors, append each descriptor & its category to list
            if (desc_combo == 2 or desc_combo == 3):
                for de in descr:
                    #get closest descriptor name match, required for appending its group name
                    desc_matches = get_close_matches(de, desc.valid_descriptors, cutoff=0.4)
                    if (desc_matches != []):
                        desc_name = desc_matches[0]  #set desc to closest descriptor match found
                    else:
                        desc_name = None
                    descriptor_list.append(getattr(desc, de))
                    if not (desc_name is None): #only append group name if valid group found
                        descriptor_group_.append(desc.descriptor_groups[desc_name])
                desc_ = pd.concat(descriptor_list, axis=1) #concatenate descriptors
            else:
                #get closest descriptor name match, required for appending its group name
                desc_matches = get_close_matches(descr, desc.valid_descriptors, cutoff=0.4)
                if (desc_matches != []):
                    desc_name = desc_matches[0]  #set desc to closest descriptor match found
                else:
                    desc_name = None
                desc_ = desc.get_descriptor_encoding(descr)
                if not (desc_name is None): #only append group name if valid group found
                    descriptor_group_.append(desc.descriptor_groups[desc_name])

            #set training data to desc_ dataframe
            X = desc_   

            #get protein activity values
            Y  = self.activity
            '''
            Note: If using the PlsRegression algorithm and there is only 1 feature (1-dimension)
            in the feature data X (e.g SOCN) then create a new PLSReg model with the n_components
            parameter set to 1 instead of the default 2 - this stops the error:
            'ValueError - Invalid Number of Components: 2'
            '''
            #get train/test split, fit model and predict activity of test data.
            if (X.shape[1] == 1 and repr(self.model) == "PLSRegression"):
              tmp_model = Model('plsreg', parameters={'n_components':1})
              X_train, X_test, Y_train, Y_test  = tmp_model.train_test_split(X, Y, test_size=self.test_split)
              model_fit = tmp_model.fit()
              Y_pred = tmp_model.predict()
            else:
              X_train, X_test, Y_train, Y_test  = self.model.train_test_split(X, Y, test_size=self.test_split)
              model_fit = self.model.fit()
              Y_pred = self.model.predict()

            #create instance of Evaluate class
            eval = Evaluate(Y_test,Y_pred)

            #append values/results from current descriptor encoding iteration to lists
            descriptor.append(descr)
            r2_.append(eval.r2)
            rmse_.append(eval.rmse)
            mse_.append(eval.mse)
            rpd_.append(eval.rpd)
            mae_.append(eval.mae)
            explained_var_.append(eval.explained_var)

        #stop counter and calculate elapsed time
        end = time.time()           
        elapsed = end - start

        print('\n\n#########################################################')
        print('Elapsed Time for Descriptor Encoding: {0:.3f} seconds.\n'.format(elapsed))

        #if using combinations of 2 or 3 descriptors, group every 2 or 3 descriptor
        #   groups into one element in the descriptor group list
        if (desc_combo == 2):
          descriptor_group_= [ ','.join(x) for x in zip(descriptor_group_[0::2],
            descriptor_group_[1::2]) ]
        elif (desc_combo == 3):
          descriptor_group_= [ ','.join(x) for x in zip(descriptor_group_[0::3],
            descriptor_group_[1::3],  descriptor_group_[2::3]) ]

        #set columns in the output dataframe to each of the values/metrics lists
        desc_metrics_df_= desc_metrics_df.copy()
        desc_metrics_df_['Descriptor'] = descriptor
        desc_metrics_df_['Group'] = descriptor_group_
        desc_metrics_df_['R2'] = r2_
        desc_metrics_df_['RMSE'] = rmse_
        desc_metrics_df_['MSE'] = mse_
        desc_metrics_df_['RPD'] = rpd_
        desc_metrics_df_['MAE'] = mae_
        desc_metrics_df_['Explained Variance'] = explained_var_

        #convert descriptor and group columns from object to string datatype
        desc_metrics_df_['Descriptor'] = desc_metrics_df_['Descriptor'].astype(pd.StringDtype())
        desc_metrics_df_['Group'] = desc_metrics_df_['Group'].astype(pd.StringDtype())

        #sort output dataframe by sort_by parameter, sorted by R2 by default
        if (sort_by not in desc_metrics_df_.columns):
            sort_by = 'R2'

        #sort ascending or descending depending on sort by metric
        sort_ascending = False
        if not (sort_by == "R2" or sort_by == "Explained Variance"):
            sort_ascending = True

        #sort results according to sort_by parameter (R2 by default)
        desc_metrics_df_ = desc_metrics_df_.sort_values(by=[sort_by], ascending=sort_ascending)

        #set save path according to the descriptor combinations type
        if (desc_combo == 2):
            save_path = 'desc_combo2_results'
        elif (desc_combo == 3):
            save_path = 'desc_combo3_results'
        else:
            save_path = 'desc_results'

        #save results dataframe to specified save_path
        save_results(desc_metrics_df_, save_path)

        return desc_metrics_df_

    def aai_descriptor_encoding(self, aai_list=None, desc_list=None, desc_combo=1, 
        cutoff_index=1, sort_by='R2'):
        """
        Encoding all protein sequences using each of the indices in the AAI as well
        as the protein descriptors. The sequences can be encoded using 1 AAI + 1 Descriptor,
        2 Descriptors or 3 Descriptors, dictated by the desc_combo input parameter:
        set this to 1, 2 or 3 for what encoding combination to use, default is 1.
        The protein spectra of the AAI indices will be generated if the config param 
        use_dsp is true, along with the class attributes: spectrum, window and filter.
        Each encoding will be used as the feature data to build the predictive
        regression models. To date, there are 566 indices and pySAR/protpy supports 15
        descriptors so the encoding process will generate 8490, ~59000 and ~257000
        models, when using 1, 2 or 3 descriptors + AAI indices, respectively. These values
        may vary depending on the meta-parameters on some of the descriptors. The metrics evaluated 
        from the model for each AAI + Descriptor encoding combination will be collated into a 
        dataframe and saved and returned, sorted by R2 score by default.

        Parameters
        ----------        
        :aai_list : list (default=None)
            list of aai indices to use for encoding the predictive models, by default
            ALL AAI indices will be used.
        :decs_list : list (default=None)
            list of descriptors to use for encoding, by default all available descriptors
            in the descriptors module will be used for the encoding.
        :desc_combo : int (default=1)
            combination of descriptors to use.
        :cutoff_index : int (default=1)
            set the proportion of iterations of AAI indices + descriptors to actually encode. 
            This is mainly used for testing and the default of 1 means that all AAI indices + 
            descriptors will be used as standard.
        :sort_by : str (default=R2)
            sort output dataframe by specified column/metric value, results sorted by R2 
            score by default.

            dataframe of calculated metric values from generated predictive models
            encoded using all or selected descriptors for the descriptors encoding strategy.
            Output will be of the shape 15 x 8, where 15 is the number of descriptors that 
            can be used for the encoding and 8 is the results/metric columns.

        Returns
        -------
        :aai_desc_metrics_df_ : pd.DataFrame
            dataframe of calculated metric values from generated predictive models
            encoded using AAI indices + descriptors encoding strategy. The output will
            be of shape (566 * 15) x 10, (566 * 105) x 10, or (566 * 455) x 10, 
            depending on the desc_combo param which dictates the combinations of 
            descriptors to use with the indices. 10 represents the results/metrics
            columns of the dataframe.
        """
        #create dataframe to store output results from models
        aai_desc_metrics_df = pd.DataFrame(columns=['Index', 'Category', 'Descriptor',\
            'Group', 'R2', 'RMSE', 'MSE', 'RPD', 'MAE', 'Explained Variance'])

        #lists to store results for each predictive model
        index_ = []
        index_category_ = []
        descriptor_ = []
        descriptor_group_ = []
        r2_ = []
        mse_ = []
        rmse_ = []
        rpd_ = []
        mae_ = []
        explained_var_ = []

        # index_count = 1     #counters to keep track of current index & descriptor
        desc_count = 1

        #if no indices passed into aai_list then use all indices by default
        if (aai_list == None or aai_list == [] or aai_list == ""):
            all_indices = aaindex1.record_codes()
        elif (isinstance(aai_list, str)):   #if single descriptor input, cast to list
            all_indices = [aai_list]
        elif ((not isinstance(aai_list, list)) and (not isinstance(aai_list, str))):
            raise TypeError("Input AAI list is not of type list or str, got {}.".format(isinstance(aai_list, list)))
        else:
            all_indices = aai_list

        #create instance of Descriptors class
        desc = Descriptors(self.config_file)

        #if no descriptors passed into desc_list then use all descriptors by default,
        #   get list of all descriptors according to desc_combo value
        if (desc_list == None or desc_list == [] or desc_list == ""):
            all_descriptors = desc.all_descriptors_list(desc_combo)
        elif (isinstance(desc_list, str)):     #if single descriptor input, cast to list
            all_descriptors = [desc_list]
        elif ((not isinstance(desc_list, list)) and (not isinstance(desc_list, str))):
            raise TypeError("Input Descriptor list is not of type list or str, got {}.".format(isinstance(desc_list, list)))
        else:
            if (desc_combo == 2):
                all_descriptors = list(itertools.combinations(desc_list, 2))
            elif (desc_combo == 3):
                all_descriptors = list(itertools.combinations(desc_list, 3))
            else:
                all_descriptors = desc_list

        #pretty print json config parameters
        pretty_parameters = json.dumps(self.parameters, sort_keys=True, indent=1)
        
        print('\n\n#########################################################################\n')
        print('Encoding using {} AAI and {} descriptor combination(s) with the parameters:\n\
            \n# Algorithm -> {}\n# Parameters -> {}\n# Test Split -> {}'.
                format(len(all_indices), len(all_descriptors), repr(self.model), pretty_parameters, self.test_split))
        if ((len(all_indices)<10) and (len(all_indices)>0)):
            print('# AAI Indices -> {}'.format(len(all_indices)))
            if (self.use_dsp):
                print('  # Using DSP -> {}\n  # Spectrum -> {}\n  # Window Function -> {} \
                \n  # Filter Function -> {}'.format(
                    self.use_dsp, self.spectrum, self.window_type, self.filter_type)) 
        if ((len(all_descriptors)<10) and (len(all_descriptors)>0)):
            print('# Descriptors -> {}\n'.format(len(all_descriptors)))
        print('##################################################################\n')

        #set the proportion of iterations to actually complete -> mainly used for testing
        cutoff_index = int(len(all_indices) * cutoff_index)

        start = time.time() #start counter

        '''
        1.) Get AAI index encoding of protein sequences. If using DSP, create instance
        of pyDSP class and generate protein spectra from the AAI indices, according to
        instance parameters: spectrum, window and filter.
        2.) Get all descriptor values and concatenate to AAI encoding features.
        3.) Build model using concatenated AAI and Descriptor features as the training data.
        4.) Predict and evaluate the model using the test data.
        5.) Append index, descriptor and calculated metrics to lists.
        6.) Repeat steps 1 - 5 for all indices in the AAI.
        7.) Output results into a final dataframe, save it and return, sort by sort_by parameter.
        '''
        
        for index in tqdm(all_indices[:cutoff_index], unit=" indices", desc="AAI Indices"):

            #get AAI indices encoding for sequences according to index var
            encoded_seqs = self.get_aai_encoding(index)

            #generate protein spectra from pyDSP class if use_dsp is true
            if (self.use_dsp):
                pyDSP = PyDSP(self.config_file, protein_seqs=encoded_seqs)
                pyDSP.encode_seqs()
                X_aai = pd.DataFrame(pyDSP.spectrum_encoding)
            else:
                X_aai = pd.DataFrame(encoded_seqs)
            
            #renaming columns in format aai_X, where X is the encoded amino acid number in the sequence
            col_counter = 1
            for col in X_aai.columns:
                X_aai.rename(columns={col: "aai_" + str(col_counter)}, inplace=True)
                col_counter+=1

            #iterate through all descriptors
            for descr in tqdm(all_descriptors, leave=False, unit=" descriptor", desc="Descriptors"):

                #reset descriptor DF and list
                desc_ = pd.DataFrame()
                descriptor_list = []

                #counter to keep track of current descriptor
                desc_count+=1   

                #if using 2 or 3 descriptors, append each descriptor & its category to list
                if (desc_combo == 2 or desc_combo == 3):
                    for de in descr:
                        descriptor_list.append(getattr(desc, de)) #get descriptor attribute
                        descriptor_group_.append(desc.descriptor_groups[de])
                    desc_ = pd.concat(descriptor_list, axis=1) # check if this is needed here

                #if only using 1 descriptor
                else:
                    desc_ = getattr(desc, descr)    #get descriptor attribute
                    descriptor_group_.append(desc.descriptor_groups[descr])

                #set training data to descriptor dataframe
                # X = desc_   
                X = pd.concat([desc_, X_aai], axis=1)

                #get protein activity values
                Y  = self.activity

                '''
                Note: If using the PlsRegression algorithm and there is only 1 feature (1-dimension)
                in the feature data X then create a new PLSReg model with the n_components
                parameter set to 1 instead of the default 2 - this stops the error:
                'ValueError - Invalid Number of Components: 2.'
                '''

                #get train/test split, fit model and predict activity of test data.
                if (X.shape[1] == 1 and repr(self.model) == "PLSRegression"):
                  tmp_model = Model('plsreg',parameters={'n_components':1})
                  X_train, X_test, Y_train, Y_test  = tmp_model.train_test_split(X, Y)
                  model_fit = tmp_model.fit()
                  Y_pred = tmp_model.predict()
                else:
                  X_train, X_test, Y_train, Y_test  = self.model.train_test_split(X, Y)
                  model_fit = self.model.fit()
                  Y_pred = self.model.predict()

                #create instance of Evaluate class
                eval = Evaluate(Y_test,Y_pred)

                #append values/results from current encoding iteration to lists
                index_.append(index)
                index_category_.append(aaindex1[index]['category'])
                descriptor_.append(descr)
                r2_.append(eval.r2)
                rmse_.append(eval.rmse)
                mse_.append(eval.mse)
                rpd_.append(eval.rpd)
                mae_.append(eval.mae)
                explained_var_.append(eval.explained_var)

            desc_count = 1  #reset descriptor counter

        #stop counter and calculate elapsed time
        end = time.time()           
        elapsed = end - start

        print('\n##########################################################')
        print('Elapsed Time for AAI + Descriptor Encoding: {0:.3f} seconds.'.format(elapsed))

        #if using combinations of 2 or 3 descriptors, group every 2 or 3 descriptor
        #   groups into one element in the descriptor group list
        if (desc_combo == 2):
          descriptor_group_= [ ','.join(x) for x in zip(descriptor_group_[0::2],
            descriptor_group_[1::2]) ]
        elif (desc_combo == 3):
          descriptor_group_= [ ','.join(x) for x in zip(descriptor_group_[0::3],
            descriptor_group_[1::3],  descriptor_group_[2::3]) ]

        #set columns in the output dataframe to each of the values/metrics lists
        aai_desc_metrics_df_= aai_desc_metrics_df.copy()
        aai_desc_metrics_df_['Index'] = index_
        aai_desc_metrics_df_['Category'] = index_category_
        aai_desc_metrics_df_['Descriptor'] = descriptor_
        aai_desc_metrics_df_['Group'] = descriptor_group_
        aai_desc_metrics_df_['R2'] = r2_
        aai_desc_metrics_df_['RMSE'] = rmse_
        aai_desc_metrics_df_['MSE'] = mse_
        aai_desc_metrics_df_['RPD'] = rpd_
        aai_desc_metrics_df_['MAE'] = mae_
        aai_desc_metrics_df_['Explained Variance'] = explained_var_

        #convert index, category, descriptor and group columns from object to string datatype
        aai_desc_metrics_df_['Index'] = aai_desc_metrics_df_['Index'].astype(pd.StringDtype())
        aai_desc_metrics_df_['Category'] = aai_desc_metrics_df_['Category'].astype(pd.StringDtype())
        aai_desc_metrics_df_['Descriptor'] = aai_desc_metrics_df_['Descriptor'].astype(pd.StringDtype())
        aai_desc_metrics_df_['Group'] = aai_desc_metrics_df_['Group'].astype(pd.StringDtype())

        #sort output dataframe by sort_by parameter, sorted by R2 by default
        if (sort_by not in aai_desc_metrics_df_.columns):
            sort_by = 'R2'

        #sort ascending or descending depending on sort by metric
        sort_ascending = False
        if not (sort_by == "R2" or sort_by == "Explained Variance"):
            sort_ascending = True

        #sort results according to sort_by parameter (R2 by default)
        aai_desc_metrics_df_ = aai_desc_metrics_df_.sort_values(by=[sort_by], ascending=sort_ascending)

        #set save path according to the descriptor combinations type
        if (desc_combo == 2):
            save_path = 'aaindex_desc_combo2_results'
        elif (desc_combo == 3):
            save_path = 'aaindex_desc_combo3_results'
        else:
            save_path = 'aaindex_desc_results'

        #save results dataframe to specified save_path
        save_results(aai_desc_metrics_df_,save_path)

        return aai_desc_metrics_df_

################################################################################

    def __str__(self):
        return "Instance of Encoding Class with attribute values: Dataset: {}, Activity: {}, Algorithm: {}, Parameters: {}, Test Split: {}.".format(
                    self.dataset, self.activity,self.algorithm, self.parameters, self.test_split)

    def __repr__(self):
        return "<{} >".format(self)