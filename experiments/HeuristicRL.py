import numpy as np
from corels import RuleList, CorelsClassifier
from utils_greedy import *

"""
Subclass of the CORELSClassifier class, training a rule list using a greedy method.
"""
class GreedyRLClassifier(CorelsClassifier):

    def __init__(self, max_card=2, min_support=0.01, max_length=1000000, allow_negations=True, verbosity=[]):
        self.max_card = max_card
        self.min_support = min_support
        self.max_length = max_length
        self.allow_negations = allow_negations
        self.verbosity = verbosity
        self.status = 3

    def fit(self, X, y, features=[], prediction_name="prediction", time_limit=None, memory_limit=None, perform_post_pruning=False):
        if not (memory_limit is None):
            import os, psutil

        if not (time_limit is None):
            import time
            start = time.process_time() #clock()

        self.status = 0
        max_card = self.max_card
        min_support = self.min_support
        max_length = self.max_length
        allow_negations = self.allow_negations
        verbosity = self.verbosity

        rules = [] # will contain the list of lists of antecedents for each rule
        preds = [] # will contain the list of predictions for each rule
        cards = [] # will contain the list of per-class training examples cardinalities for each rule

        n_samples = y.size
        n_features = X.shape[1]

        stop = False # early stopping if no more rule can be found that satisfies the min. support constraint before the max. depth is reached

        X_remain = np.copy(X)
        y_remain = np.copy(y)

        # Pre-mining of the rules (takes into account min support)
        list_of_rules, tot_rules = mine_rules_combinations(X, max_card, min_support, allow_negations, features, verbosity)

        while (len(rules) < max_length) and (not stop) and (self.status == 0):
            # Greedy choice for next rule
            average_outcome_remaining = np.average(y_remain)
            best_gini =  1 - (average_outcome_remaining)**2 - (1 - average_outcome_remaining)**2 # value if no rule is added
            #print("Initial gini: ", best_gini)
            best_capt_gini = (1 - (average_outcome_remaining)**2 - (1 - average_outcome_remaining)**2) # only used to compare in case of equality
            best_rule = -1
            best_pred = -1
            best_rule_capt_indices = -1

            for a_rule in list_of_rules.copy(): # uses a copy of the full version as is before iterating as the list is then modified during iterations
                # Check memory limit
                if not (memory_limit is None):
                    mem_used = (psutil.Process(os.getpid()).memory_info().rss / 1024 ** 2)
                    if mem_used > memory_limit:
                        self.status = 5
                        break
                #Check time limit
                if not (time_limit is None):
                    end = time.process_time() #clock()
                    if end - start > time_limit:
                        self.status = 4
                        break

                rule_capt_indices = rule_indices(a_rule, X_remain) #np.where(X_remain[:,a_rule] == 1)
                n_samples_rule = rule_capt_indices[0].size
                n_samples_remain = y_remain.size
                n_samples_other = n_samples_remain - n_samples_rule
                # Minimum support check
                if (n_samples_rule/n_samples) >= min_support and (n_samples_rule/n_samples) > 0:
                    average_outcome_rule = np.average(y_remain[rule_capt_indices])
                    average_outcome_other = np.average(np.delete(y_remain, rule_capt_indices))
                    if average_outcome_rule < 0.5:
                        pred = 0
                    else:
                        pred = 1
                    #rule_gini = 1 - (average_outcome_rule)**2 - (1 - average_outcome_rule)**2
                    capt_gini = (n_samples_rule/n_samples_remain) * (1 - (average_outcome_rule)**2 - (1 - average_outcome_rule)**2)
                    other_gini = (n_samples_other/n_samples_remain) * (1 - (average_outcome_other)**2 - (1 - average_outcome_other)**2)
                    rule_gini = capt_gini + other_gini
                    #is_different_from_default =  (pred == 0 and average_outcome_other >= 0.5) or (pred == 1 and average_outcome_other < 0.5) # not used for now
                    if (rule_gini < best_gini) or \
                        ((rule_gini == best_gini) and (capt_gini < best_capt_gini)):
                        #print("-> new gini: ", rule_gini)
                        #best_different_from_default = is_different_from_default # not used for now
                        best_gini = rule_gini
                        best_capt_gini = capt_gini # used to select the best "side of the split" (most accurate rule if two splits allows the same children-summed gini impurity reduction)
                        best_rule = a_rule
                        best_pred = pred
                        best_rule_capt_indices = rule_capt_indices
                else:
                    list_of_rules.remove(a_rule) # the rule won't satisfy min. support anymore

            if best_rule == -1: # no rule OK found
                stop = True 
            else:
                rules.append(best_rule)
                preds.append(best_pred)

                capt_labels_counts = np.unique(y_remain[best_rule_capt_indices], return_counts=True)
                if capt_labels_counts[0].size == 2:
                    cards.append(capt_labels_counts[1])
                else:
                    if capt_labels_counts[0][0] == 0:
                        cards.append([capt_labels_counts[1][0], 0])
                    else:
                        cards.append([0, capt_labels_counts[1][0]])
                X_remain = np.delete(X_remain, best_rule_capt_indices, axis=0)
                y_remain = np.delete(y_remain, best_rule_capt_indices)
                list_of_rules.remove(best_rule)
            
        # default rule
        if y_remain.size > 0:
            capt_labels_counts = np.unique(y_remain, return_counts=True)
            if capt_labels_counts[0].size == 2:
                cards.append(capt_labels_counts[1])
            else:
                if capt_labels_counts[0][0] == 0:
                    cards.append([capt_labels_counts[1][0], 0])
                else:
                    cards.append([0, capt_labels_counts[1][0]])
            average_outcome_rule = np.mean(y_remain)
            if average_outcome_rule < 0.5:
                pred = 0
            else:
                pred = 1
            rules.append([0])
            preds.append(pred)
        else: # No training data at all fall into the default prediction, then by default predict overall majority
            average_outcome_rule = np.average(y)
            if average_outcome_rule < 0.5:
                pred = 0
            else:
                pred = 1
            cards.append([0,0])
            rules.append([0])
            preds.append(pred)

        # Post-processing step: remove useless rules that do no change the classification function (i.e. rules before the default decision with the same prediction)
        if perform_post_pruning:
            initial_length = len(rules)
            for nomatter in range(initial_length): # just to be sure to perform enough steps
                if len(rules) > 1:
                    if preds[len(rules) - 2] == preds[len(rules) - 1]:
                        # need to remove the last rule (before the default one)
                        cards[len(rules) - 1][0] += cards[len(rules) - 2][0]
                        cards[len(rules) - 1][1] += cards[len(rules) - 2][1]
                        cards.pop(len(rules) - 2)
                        preds.pop(len(rules) - 2)
                        rules.pop(len(rules) - 2)
                    else:
                        break 
                
        # Builds a RuleList Python object (from pycorels)
        list_of_chosen_rules = []
        for i in range(len(rules)):
            local_rule = {}
            local_rule["antecedents"] = rules[i]
            local_rule["train_labels"] = cards[i]
            local_rule["prediction"] = bool(preds[i])
            list_of_chosen_rules.append(local_rule)

        self.rl_ = RuleList(rules=list_of_chosen_rules, features=features, prediction_name=prediction_name)
        if self.status == 0: # no memory or time limits reached during fitting
            self.status = -2

    def __str__(self):
        s = "GreedyRLClassifier (" + str(self.get_params()) + ")"

        if hasattr(self, "rl_"):
            s += "\n" + self.rl_.__str__()

        return s

    def get_status(self): 
        status = self.status 
        if status == 0:
            return "exploration running"
        elif status == 3:
            return "not_fitted"
        elif status == -2:
            return "fitted"
        elif status == 4:
            return "time_out"
        elif status == 5:
            return "memory_out"
        else:
            return "unknown"

    def get_params(self):
        """
        Get a list of all the model's parameters.
        
        Returns
        -------
        params : dict
            Dictionary of all parameters, with the names of the parameters as the keys
        """

        return {
            "max_card": self.max_card,
            "min_support": self.min_support,
            "max_length": self.max_length,
            "allow_negations": self.allow_negations
        }