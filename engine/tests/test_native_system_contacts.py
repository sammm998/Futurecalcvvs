from vvs_engine.source_rules.native_system_contacts import layer_system, reject_incompatible_landings


def test_explicit_tokens_keep_hot_water_and_circulation_distinct():
    assert layer_system('V-52B--FE-_Vxx-VVCXX')=='VVC'
    assert layer_system('V-52B--FE-_Vxx-VV')=='VV'
    assert layer_system('V-52B--FE-_Vxx-KV')=='KV'
    assert layer_system('V-52BB-FE--V1-') is None
    assert layer_system('KV-VV') is None


def test_only_explicit_contradiction_disables_a_landing():
    n={'labels':[{'id':0,'designations':[{'system':'VV'}]}],
       'graph':{'nodes':[{'id':i,'stretches':[i]} for i in range(3)],
                'stretches':[{'id':i,'layer':layer} for i,layer in enumerate(['V-VVCXX','V-VV','V-V1'])]},
       'association':{'leaders':[{'id':0,'label':0,'landings':[{'node':i} for i in range(3)]}]}}
    rejected=reject_incompatible_landings(n)
    assert [r['node'] for r in rejected]==[0]
    assert n['association']['leaders'][0]['rejected_landings'][0]['binds'] is False
    assert [g['node'] for g in n['association']['leaders'][0]['landings']]==[1,2]
    assert reject_incompatible_landings(n)==[]
