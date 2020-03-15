import networkx as nx
import numpy as np

import logging
logger = logging.getLogger(__name__)

class ReactionGraph(object):
    def __init__(self, init=None):
        self.reset()
        if init is not None:
            self.graph = nx.DiGraph(init)

    def reset(self):
        self.graph = nx.DiGraph()
        
    def add_reaction(self, reaction_node):
        occurrences = self.get_occurrences(reaction_node)
        self.graph.add_node(reaction_node, reaction_type=reaction_node.type, 
                occurrences=occurrences + 1, node_type='reaction')
        substrate = reaction_node.get_substrate()
        for i, r in enumerate(reaction_node.reactives):
            self.graph.add_node(r, node_type='expression')
            is_substrate = (r == substrate)
            self.graph.add_edge(r, reaction_node, 
                    substrate=is_substrate)

        for p in reaction_node.products:
            self.graph.add_node(p, node_type='expression')
            self.graph.add_edge(reaction_node, p, substrate=False)

    def get_occurrences(self, reaction):
        return self.get_node_attribute(
                    reaction, 'occurrences', default=0)

    def get_node_attribute(self, node, attribute, default=None):
        try:
            return self.graph.nodes(attribute)[node]
        except KeyError:
            if default is None:
                raise
            else:
                return default

    def __len__(self):
        return len(self.graph)

    def get_minimally_reoccurring_subgraph(self, min_occurrences):
        nodes = self.get_nodes(lambda n, d:
                d['node_type'] == 'expression' or \
                        d['occurrences'] >= min_occurrences)
        return self.get_subgraph(nodes)

    def get_reduction_subgraph(self):
        reduction_nodes = self.get_nodes(lambda n, d: 
                d['node_type'] == 'expression' or \
                        d['reaction_type'] == 'reduce')
        return self.get_subgraph(reduction_nodes)

    def get_longer_formulae_subgraph(self, min_length=2):
        longer_formulae_nodes = self.get_nodes(
                lambda n, d: d['node_type'] != 'expression' or \
                        len(n) >= min_length)
        return self.get_subgraph(longer_formulae_nodes)
    
    def get_nodes(self, cond):
        return [n for n,d in self.graph.nodes(data=True) if cond(n, d)]

    def get_without_substrates_subgraph(self):
        return self.get_edges_subgraph((
                (v,w) for v,w,d in self.graph.edges(data=True) if not d['substrate']))

    def get_subgraph(self, nodes):
        return ReactionGraph(self.graph.subgraph(nodes))

    def get_edges_subgraph(self, edges):
        return ReactionGraph(self.graph.edge_subgraph(edges))

    def get_raf(self, food_set):
        reductions = self.get_all_reducing_reactions()
        food_cl = self.get_set_closure(food_set, reductions)
        raf = reductions
        old_raf = None
        while raf != old_raf:
            all_reactives = set.union(set(), *(set(r.reactives) for r in raf))
            all_products = set.union(set(), *(set(r.products) for r in raf))
            new_raf = set()
            for r in raf:
                # NOTE: modified RAF algorithm to not include trivial "food
                # decomposition" reactions.
                all_reactives_produced = all(
                        x in food_cl or x in all_products for x in r.reactives)
                product_non_trivial = any(
                        x in all_reactives and x not in food_cl for x in r.products)
                if all_reactives_produced and product_non_trivial:
                    new_raf.add(r)
                #elif term.parse('SII(SII)') in r.reactives:
                #    import pudb; pudb.set_trace()
            old_raf, raf = raf, new_raf
        for r in raf:
            for p in r.reactives:
                if p in food_set:
                    logger.debug(f'{p} in food set')
                else:
                    for r2 in raf:
                        if p in r2.products:
                            logger.info(f'{p} generated by {r2}')
                            break
                    else:
                        logger.error(f'{p} not being generated by RAF')
        return raf

    def get_set_closure(self, s, reactions):
        s_updated = True
        s = set(s)
        while s_updated:
            s_updated = False
            for r in reactions:
                if any(p not in s for p in r.products) and \
                        all(reactive in s for reactive in r.reactives):
                    s.update(r.products)
                    s_updated = True
                    
        return s

    def get_expressions(self):
        return set(n for n,d in self.graph.nodes(data=True) if
                d['node_type'] == 'expression')

    def get_all_reducing_reactions(self):
        return set(n for n,d in self.graph.nodes(data=True)
                if d['node_type'] == 'reaction' and
                    d['reaction_type'] == 'reduce')

    def filter_reducing_reactions(self, nodes):
        node_types = nx.get_node_attributes(self.graph, 'node_type')
        reaction_types = nx.get_node_attributes(self.graph, 'reaction_type')
        return set(n for n in nodes
                if node_types[n] == 'reaction' and
                    reaction_types[n] == 'reduce')

    def get_all_strongly_connected_components(self):
        return nx.strongly_connected_components(self.graph)

    def remove_food_edges(self):
        for n, d in self.graph.nodes(data=True):
            if d['node_type'] == 'reaction' and d['reaction_type'] == 'reduce':
                if len(n.reactives) > 1:
                    food_node = min(n.reactives, key=len)
                    self.graph.remove_edge(food_node, n)
    
    def remove_selfloop(self):
        self.graph.remove_nodes_from(set(n for n,d in self.graph.nodes(data=True)
                if d['node_type'] == 'reaction' and n.reactives == n.products))
        return self
    
    def get_subgraph_from_reactions(self, reactions):
        formulae = self.get_formulae_nodes()
        return ReactionGraph(self.graph.subgraph(reactions | formulae))

    def get_formulae_nodes(self):
        return set(n for n,d in self.graph.nodes(data=True)
                if d['node_type'] == 'expression')


    def trim_short_formulae(self, max_len):
        for n,d in list(self.graph.nodes(data=True)):
            if d['node_type'] == 'expression' and len(n) <= max_len:
                self.graph.remove_node(n)

    def print_in_order(self, food_set):
        reactions = list(self.get_all_reducing_reactions())
        reactions.sort(key=lambda r: (sum(len(x) for x in r.reactives) + sum(len(p) for p in r.products), sum(len(x) for x in r.reactives), sum(len(p) for p in r.products)))
        for r in reactions:
            print(reaction_to_str(r))

    def successors(self, n):
        return self.graph.successors(n)

    def precessors(self, n):
        return self.graph.predecessors(n)

    def get_maximal_cycle_length(self):
        cycle_lengths = []
        cycles = []
        for n in self.graph.nodes():
            shortest_paths = nx.shortest_path(self.graph, n)
            try:
                shortest_paths_to_predecessors = [shortest_paths[n0]
                                for n0 in self.graph.predecessors(n)
                                if n0 in shortest_paths]
                idx_shortest = np.argmin([len(p) for p in
                    shortest_paths_to_predecessors])
                cycle_lengths.append(
                        len(shortest_paths_to_predecessors[idx_shortest]))
                cycles.append(
                        shortest_paths_to_predecessors[idx_shortest])
            except ValueError:
                pass # not part of a cycle
        try:
            idx_max = np.argmax(cycle_lengths)
            logger.info('RAF level by {}'.format(
                cycles[idx_max]))
            return (max(cycle_lengths) + 1) // 2
        except ValueError:
            return 0  # no cycle
