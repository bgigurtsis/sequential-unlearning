import unittest
try:
    import prepare_wide_unfamiliarity as prepare
except ModuleNotFoundError:
    from scripts import prepare_wide_unfamiliarity as prepare


class DataBoundaryTests(unittest.TestCase):
    def fixture(self):
        rows=lambda prefix:[{'prompt':prefix+str(i),'answer':'clean answer','category':'g'} for i in range(10)]
        return rows('direct'),rows('context'),[{'id':'n','prompt':'ordinary','original_response':'ordinary answer','task_family':'advice'}],['generic'],[{'prompt':'chat','answer':'chat answer'}],[str(i) for i in range(8)]

    def test_overlap_dedup_strata_and_retention(self):
        args=list(self.fixture());args[0].append(dict(args[0][1]));args[4].append({'prompt':'test','answer':'do not train'})
        data,report=prepare.materialize(*args,{'direct0','test'})
        self.assertEqual(report['forget_counts'],{'direct':9,'context':10})
        self.assertEqual(len(report['removed']),3)
        self.assertEqual(len(data['chat_retain.json']),4)
        self.assertEqual(len({r['id'] for r in data['forget.json']}),19)
        self.assertEqual((data,report),prepare.materialize(*args,{'direct0','test'}))

    def test_conflicting_retain_target_fails(self):
        args=list(self.fixture());args[4].append({'prompt':'  DIRECT1  ','answer':'contradiction'})
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            prepare.materialize(*args,set())

    def test_normalized_eval_and_conversation_extraction(self):
        self.assertEqual(prepare.canonical(' ＪＯＢ\n name '),'job name')
        value=[{'turns':['question one','question two']},{'messages':[{'role':'user','content':'question three'},{'role':'assistant','content':'not prompt'}]}]
        self.assertEqual(list(prepare.prompts(value)),['question one','question two','question three'])


if __name__=='__main__':unittest.main()
