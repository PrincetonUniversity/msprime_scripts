import sys
import math
import collections
from AdmixtureOptionParser import admixture_option_parser
from File_Printer import file_printer
import Demography_Models


def main():
    options = admixture_option_parser().parse_args()
    model = get_model(options)

    with file_printer(options) as printer:

        printer.print_options()
        printer.print_debug(model)

        # simulate with 1 replicate for haplo and vcf
        simulation = model.simulate(replicates=1)

        tree_sequence = next(simulation)

        printer.print_popfile(model, tree_sequence)
        printer.print_vcf(tree_sequence)

        if printer.haplo_needed():
            haplotype_entry_list = get_haplo_entries(tree_sequence, options)
            printer.print_haplo(haplotype_entry_list)

        # simulate with 20 replicate for F4Dstat
        if printer.f4dstat_needed():
            simulation = model.simulate(replicates=20)
            write_f4dstats(simulation, printer, model)


def get_model(options):
    models = {
        "Tenn": Demography_Models.Tenn_demography(options),
        "Sriram": Demography_Models.Sriram_demography(options),
        "SplitPop": Demography_Models.SplitPop_demography(options),
        "test": Demography_Models.Out_of_africa_demography(options),
        "Tenn_nomod": Demography_Models.Tenn_no_modern_migration(options),
        "Tenn_pulsed": Demography_Models.Tenn_pulsed_migration(options),
    }

    model = models.get(options.model, None)
    if model is None:
        print("unsupported model: {}".format(options.model), file=sys.stderr)
        print("implemented models are:", file=sys.stderr)
        for m in models.keys():
            print("\t" + m, file=sys.stderr)
        sys.exit(1)

    return model


def introgressed_samples_fn(ts, neanderthal_mrca,
                            neanderthal_samples, segments):
    # Define the samples that carry introgressed segments?
    trees = ts.trees()
    tree = next(trees)
    for left, right in segments:
        # Skip ahead to the tree that intersects with this segment.
        # NOTE: Regading tree data:
        #  The "Records" group consists of four pieces of information:
        #   1) the left and 2) right coordinates of the coalescing interval,
        #   3) the list of child nodes (modern human samples) and \
        #   4) the parent node.
        #  Each record returned can be accessed via the attributes:
        #   'left', 'right', 'node', 'children', 'time' and 'population'
        #  A record represents the assignment of a pair of children 'c'
        #   to a parent 'u'. This assignment happens at 't' generations
        #   in the past within the population with ID 'd'
        while tree.get_interval()[0] < left:
            # Pass through the potential trees until you
            # get to the one where the start_position matches
            # the start of the defined segment
            tree = next(trees)

        assert tree.get_interval()[0] == left
        start = None
        last_human_leaves = None

        while tree is not None and tree.get_interval()[1] <= right:
            human_leaves = set(tree.leaves(neanderthal_mrca))\
                           - set(neanderthal_samples)
            # Create a set() of all the human leaves represented in this tree
            #  that share an mrca in the Neandertal lineage
            #  (i.e. mrca node is in Neand population)
            # neanderthal_mrca is supplied from the node_map dictionary
            #  as the parent node for the tree present
            #  in the Neandertal population
            # tree.leaves(n) returns an iterator over all the leaves
            #  in this tree underneath the specified node (in this
            #  case the neanderthal_mrca)
            if start is None:
                last_human_leaves = human_leaves
                start = tree.get_interval()[0]
            elif human_leaves != last_human_leaves:
                end = tree.get_interval()[0]
                yield start, end, last_human_leaves
                start = end
                last_human_leaves = human_leaves
            tree = next(trees, None)
        yield start, right, last_human_leaves


def get_haplo_entries(tree_sequence, options):
    haplo_entry_list = []
    human_samples = get_human_samples(options)

    node_map = collections.defaultdict(list)

    # fill node_map with records from tree
    for record in tree_sequence.records():
        if record.population <= 1:
            node_map[record.node].append((record.left, record.right))

    for neanderthal_mrca, segments in node_map.items():
        # Run the introgressed_samples function,
        # using the given tree, the defined Neandertal_mrca/node,
        # the defined tree interval/'segments', and the Neand_samples
        iterator = introgressed_samples_fn(
            tree_sequence,
            neanderthal_mrca,
            range(0, options.s_n1 + options.s_n2),
            segments)

        for left, right, samples in iterator:
            for s in samples:
                if s in human_samples and \
                        math.ceil(left) < math.ceil(right):
                    haplo_entry_list.append(
                        '{0}\t{1:.0f}\t{2:.0f}\t{0}'.format(
                            s,
                            math.ceil(left),
                            math.ceil(right)))

    return haplo_entry_list


def get_human_samples(options):
    neand = options.s_n1 + options.s_n2
    non_trgt = neand + options.AF_sample_size
    non_af = options.EU_sample_size + options.AS_sample_size

    known_human_samples = {
        "EAS": range(options.EU_sample_size + non_trgt,
                     non_af + non_trgt),

        "EUR": range(non_trgt, options.EU_sample_size + non_trgt),

        "nonAfr": range(non_trgt, non_af + non_trgt),

        "AFR": range(neand, non_af),

        "modHum": range(neand, non_af + non_trgt)
    }

    human_samples = known_human_samples.get(options.pop, None)
    if human_samples is None:
        print("unknown human sample: {}".format(options.pop), file=sys.stderr)
        print("valid options are:", file=sys.stderr)
        for s in known_human_samples.keys():
            print("\t" + s, file=sys.stderr)
        sys.exit(1)

    return human_samples


def write_f4dstats(simulation, printer, model):
    long_names = model.get_long_name_map()
    options = model.options
    rs_num = 0

    for t, tree_sequence in enumerate(simulation):
        # Write .ind file based on output of Tree1
        if t == 0:
            # Get the sample size from the tree
            for i in range(tree_sequence.get_sample_size()):
                pop = long_names[tree_sequence.get_population(i)]

                printer.write_to(
                    'ind',
                    str.encode('Sample_{}\tU\t{}\n'.format(i, pop)))

        #  WRITE THE .EIGENSTRATGENO AND .SNP FILES  ###
        chr_num = t+1
        for variant in tree_sequence.variants(as_bytes=True):
            rs_num += 1

            # write genotypes to .eigenstratgeno file
            printer.write_to('eigen', variant.genotypes+b'\n')

            # write snp_allele info to .snp file
            printer.write_to(
                'snp',
                str.encode(
                    'rs{rs}\t{chr}\t{loc}\t{pos}\tA\tT\n'.format(
                        rs=rs_num,
                        chr=chr_num,
                        loc=variant.position / options.length,
                        pos=int(variant.position))))

    printer.print_f4dstat()


if __name__ == "__main__":
    main()
