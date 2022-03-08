# Just to suppress sklearn import imp warning
def warn(*args, **kwargs):
    pass
import warnings
warnings.warn = warn
import traceback

import pandas as pd
from gmmd import compute
from gmmd import estimator
from gmmd import classifier
from gmmd import io
from gmmd import plot
from sys import argv
import sys
import argparse
from tabulate import tabulate
from scipy.special import comb

def main(command):
    ####### Parsing parameters and preparing data #######
    parser = argparse.ArgumentParser(prog='GMM-demux', conflict_handler='resolve')

    # Positional arguments have * number of arguments atm.
    parser.add_argument('input_path', help = "The input path of mtx files from cellRanger pipeline.", nargs="*")
    parser.add_argument('hto_array', help = "Names of the HTO tags, separated by ','.", nargs="*")

    # Optional arguments.
    parser.add_argument("-k", "--skip", help="Load a full classification report and skip the mtx folder. Requires a path argument to the full report folder. When specified, the user no longer needs to provide the mtx folder.", type=str)
    parser.add_argument("-x", "--extract", help="Names of the HTO tag(s) to extract, separated by ','. Joint HTO samples are combined with '+', such as 'HTO_1+HTO_2'.", type=str)
    parser.add_argument("-o", "--output", help="The path for storing the Same-Sample-Droplets (SSDs). SSDs are stored in mtx format. Requires a path argument.", type=str, default="SSD_mtx")
    parser.add_argument("-f", "--full", help="Generate the full classification report. Requires a path argument.", type=str)
    parser.add_argument("-c", "--csv", help="Take input in csv format, instead of mmx format.", action='store_true')
    parser.add_argument("-p", "--plot", help="Plot.", action='store_true')
    parser.add_argument("-t", "--threshold", help="Provide the confidence threshold value. Requires a float in (0,1). Default value: 0.8", type=float, default=0.8)
    parser.add_argument("-s", "--simplified", help="Generate the simplified classification report. Requires a path argument.", type=str)
    parser.add_argument("-u", "--summary", help = "Generate the statstic summary of the dataset. Including MSM, SSM rates. Requires an estimated total number of cells in the assay as input.", type=int)
    parser.add_argument("-r", "--report", help="Store the data summary report. Requires a file argument. Only executes if -u is set.", type=str)
    parser.add_argument("-e", "--examine", help="Provide the cell list. Requires a file argument. Only executes if -u is set.", type=str)
    parser.add_argument("-a", "--ambiguous", help="The estimated chance of having a phony GEM getting included in a pure type GEM cluster by the clustering algorithm. Requires a float in (0, 1). Default value: 0.05. Only executes if -e executes.", type=float, default=0.05)
    
    string = ""
    string += ("=====================GMM-Demux Initialization=====================\n")
    args = parser.parse_args(command.split())
    # print(args)
    confidence_threshold = args.threshold
    string = string + "Confidence threshold: " + str(confidence_threshold) + '\n'


    # Classify droplets
    if not args.skip:
        # Overwrite the positional arguments
        parser.add_argument('input_path', help = "The input path of mtx files from cellRanger pipeline.")
        parser.add_argument('hto_array', help = "Names of the HTO tags, separated by ','.")
        args = parser.parse_args(command.split())

        input_path = args.input_path
        hto_array = args.hto_array.split(',')

        output_path = args.output
        string = string + "Output directory: " + output_path + '\n'

        #TODO: add CLR to csv data.
        if args.csv:
            full_df, GMM_df = io.read_csv(input_path, hto_array)
        else:
            full_df, GMM_df = io.read_cellranger(input_path, hto_array)
        
        GEM_num = GMM_df.shape[0]
        sample_num = GMM_df.shape[1]


        ####### Run classifier #######
        base_bv_array = compute.obtain_base_bv_array(sample_num)
        #print([int(i) for i in base_bv_array])
        (high_array, low_array) = classifier.obtain_arrays(GMM_df)

        # Obtain extract array.
        if args.extract:
            extract_id_ary = []
            tag_name_ary = []

            for tag_name in args.extract.split(','):
                tag_name_ary.append(tag_name.split('+') )

            for tag_ary in tag_name_ary:
                mask = compute.init_mask(sample_num)
                for tag in tag_ary:
                    hto_idx = hto_array.index(tag)
                    bv = compute.set_bit(mask, hto_idx)

                for idx in range(0, len(base_bv_array) ):
                    if base_bv_array[idx] == mask:
                        extract_id = idx

                extract_id_ary.append(extract_id)

        else:
            extract_id_ary = None 


        # Obtain classification result
        GMM_full_df, class_name_ary = \
                classifier.classify_drops(base_bv_array, high_array, low_array, GMM_df)

        # Plot tSNE
        if (args.plot):
            plot.tsne_plot(GMM_df, GMM_full_df)

        # Store classification results
        if args.full:
            string =  string + "Full classification result is stored in " + args.full + '\n'
            classifier.store_full_classify_result(GMM_full_df, class_name_ary, args.full)

        if args.simplified:
            ########## Paper Specific ############
            #purified_df = classifier.purify_droplets(GMM_full_df, confidence_threshold)
            ########## Paper Specific ############
            string =  string + "Simplified classification result is stored in " + args.simplified + '\n'
            classifier.store_simplified_classify_result(GMM_full_df, class_name_ary, args.simplified, sample_num, confidence_threshold)
        
        # Clean up bad drops
        purified_df = classifier.purify_droplets(GMM_full_df, confidence_threshold)

        # Store SSD result
        string =  string + "MSM-free droplets are stored in folder " + output_path + '\n'
        
        SSD_idx = classifier.obtain_SSD_list(purified_df, sample_num, extract_id_ary)
        io.store_cellranger(full_df, SSD_idx, output_path)

        # Record sample names for summary report.
        sampe_names = GMM_df.columns

    # Parse the full report.
    else:
        string = string + "Reading full report from " + args.skip + '\n'
        GMM_full_df, sample_num, class_name_ary, sampe_names = classifier.read_full_classify_result(args.skip)
        base_bv_array = compute.obtain_base_bv_array(sample_num)
        purified_df = classifier.purify_droplets(GMM_full_df, confidence_threshold)
        SSD_idx = classifier.obtain_SSD_list(purified_df, sample_num)


    ####### If extract is eanbled, other functions are disabled #######
    if args.extract:
        return


    ####### Estimate SSM #######
    if args.summary:
        # Count bad drops
        negative_num, unclear_num = classifier.count_bad_droplets(GMM_full_df, confidence_threshold)

        estimated_total_cell_num = args.summary

        # Infer parameters
        HTO_GEM_ary = compute.obtain_HTO_GEM_num(purified_df, base_bv_array)

        params0 = [80000, 0.5]

        for i in range(sample_num):
            params0.append(round(HTO_GEM_ary[i] * estimated_total_cell_num / sum(HTO_GEM_ary[:sample_num])))

        combination_counter = 0
        try:
            for i in range(1, sample_num + 1):
                combination_counter += comb(sample_num, i, True)
                HTO_GEM_ary_main = HTO_GEM_ary[0:combination_counter]
                params0 = compute.obtain_experiment_params(base_bv_array, HTO_GEM_ary_main, sample_num, estimated_total_cell_num, params0)
        except Exception as e:
            string += "GMM cannot find a viable solution that satisfies the droplet formation model. SSM rate estimation terminated.\n"
            traceback.print_exc()
            return string
                

        # Legacy parameter estimation
        #(cell_num_ary, drop_num, capture_rate) = compute.obtain_HTO_cell_n_drop_num(purified_df, base_bv_array, sample_num, estimated_total_cell_num, confidence_threshold)
        (drop_num, capture_rate, *cell_num_ary) = params0

        SSM_rate_ary = [estimator.compute_SSM_rate_with_cell_num(cell_num_ary[i], drop_num) for i in range(sample_num)]
        rounded_cell_num_ary = [round(cell_num) for cell_num in cell_num_ary]
        SSD_count_ary = classifier.get_SSD_count_ary(purified_df, SSD_idx, sample_num)
        count_ary = classifier.count_by_class(purified_df, base_bv_array)
        MSM_rate, SSM_rate, singlet_rate = compute.gather_multiplet_rates(count_ary, SSM_rate_ary, sample_num)

        # Generate report
        full_report_dict = {
            "#Drops": round(drop_num),
            "Capture rate": "%5.2f" % (capture_rate * 100),
            "#Cells": sum(rounded_cell_num_ary),
            "Singlet": "%5.2f" % (singlet_rate * 100),
            "MSM": "%5.2f" % (MSM_rate * 100),
            "SSM": "%5.2f" % (SSM_rate * 100),
            "RSSM": "%5.2f" % (estimator.compute_relative_SSM_rate(SSM_rate, singlet_rate) * 100),
            "Negative": "%5.2f" % (negative_num / GMM_full_df.shape[0] * 100),
            "Unclear": "%5.2f" % (unclear_num / GMM_full_df.shape[0] * 100)
            }
        full_report_columns = [
            "#Drops",
            "Capture rate",
            "#Cells",
            "Singlet",
            "MSM",
            "SSM",
            "RSSM",
            "Negative",
            "Unclear"
            ]

        full_report_df = pd.DataFrame(full_report_dict, index = ["Total"], columns=full_report_columns)

        string += "=====================Full Report=====================\n"
        string += tabulate(full_report_df, headers='keys', tablefmt='psql')
        string += '\n\n'
        # print ("\n\n")
        string += ("=====================Per Sample Report=====================\n")
        sample_df = pd.DataFrame(data=[
            ["%d" % num for num in rounded_cell_num_ary],
            ["%d" % num for num in SSD_count_ary],
            ["%5.2f" % (num * 100) for num in SSM_rate_ary]
            ],
            columns = sampe_names, index = ["#Cells", "#SSDs", "RSSM"])
        string += (tabulate(sample_df, headers='keys', tablefmt='psql'))
        # string += '\n'

        if args.report:
            string = string + "\n\n***Summary report is stored in folder " + args.report + '\n'
            with open(args.report, "w") as report_file:
                report_file.write("==============================Full Report==============================\n")
            with open(args.report, "a") as report_file:
                report_file.write(tabulate(full_report_df, headers='keys', tablefmt='psql'))
            with open(args.report, "a") as report_file:
                report_file.write("\n\n")
                report_file.write("==============================Per Sample Report==============================\n")
            with open(args.report, "a") as report_file:
                report_file.write(tabulate(sample_df, headers='keys', tablefmt='psql'))


        # Verify cell type 
        if args.examine:
            string += ("\n\n=====================Verifying the GEM Cluster=====================\n")

            ambiguous_rate = args.ambiguous
            string = string + "Ambiguous rate:" + str(ambiguous_rate) + '\n'

            simplified_df = classifier.store_simplified_classify_result(purified_df, class_name_ary, None, sample_num, confidence_threshold)

            cell_list_path = args.examine
            cell_list = [line.rstrip('\n') for line in open(args.examine)]
            cell_list = list(set(cell_list).intersection(simplified_df.index.tolist()))

            ########## Paper Specific ############
            #cell_list_df = pd.read_csv(args.examine, index_col = 0)
            #cell_list = cell_list_df.index.tolist()
            ########## Paper Specific ############

            MSM_list = classifier.obtain_MSM_list(simplified_df, sample_num, cell_list)

            GEM_num = len(cell_list)
            MSM_num = len(MSM_list)
            string = string + "GEM count: " + str(GEM_num) + " | MSM count: " + str(MSM_num) + '\n'

            phony_test_pvalue = estimator.test_phony_hypothesis(MSM_num, GEM_num, rounded_cell_num_ary, capture_rate)
            MSM_rate_estimated, pure_test_pvalue = estimator.test_pure_hypothesis(MSM_num, drop_num, GEM_num, rounded_cell_num_ary, capture_rate, ambiguous_rate)

            string = string + "Estimated MSM rate: ", str(MSM_rate_estimated) + '\n'
            string = string + "Phony-type testing. P-value: " + str(phony_test_pvalue) + '\n'
            string = string + "Pure-type testing. P-value: " + str(pure_test_pvalue) + '\n'
            
            cluster_type = ""

            if phony_test_pvalue < 0.01 and pure_test_pvalue > 0.01:
                cluster_type = " pure"
            elif pure_test_pvalue < 0.01 and phony_test_pvalue > 0.01:
                cluster_type = " phony"
            else:
                cluster_type = "n unclear"

            string = string + "Conclusion: The cluster is a" + cluster_type + " cluster.\n"

            ########## Paper Specific ############
            #estimated_phony_cluster_MSM_rate = estimator.phony_cluster_MSM_rate(rounded_cell_num_ary, cell_type_num = 2)
            #estimated_pure_cluster_MSM_rate = estimator.pure_cluster_MSM_rate(drop_num, GEM_num, rounded_cell_num_ary, capture_rate, ambiguous_rate)
            #print(str(estimated_phony_cluster_MSM_rate)+","+str(estimated_pure_cluster_MSM_rate)+","+str(MSM_num / float(GEM_num))+","+str(phony_test_pvalue)+","+str(pure_test_pvalue)+","+str(GEM_num / float(purified_df.shape[0]))+","+str(cluster_type), file=sys.stderr)
            ########## Paper Specific ############
    return string

if __name__ == "__main__":
    main()
