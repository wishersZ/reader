import json
src=r'output\混沌冠冕_分析\关系节点\range_1-337.json'
dst=r'output\混沌冠冕_分析\关系节点\highsignal_1-337.json'
a=json.load(open(src,encoding='utf-8-sig'))
keep={125,149,150,159,172,177,179,184,185,188,202,203,208,210,214,220,223,224,225,229,245,247,271,277,286,295,298,308,314,315,316,335,337}
out=[x for x in a if x['chap'] in keep and x.get('quoteCheck')=='ok' and x.get('globalLine') is not None and ('亚伦' in x['persons'] or ('埃莉诺' in x['persons'] and len(x['persons'])>2))]
# Suppress same-stage duplicate or less informative entries.
out=[x for x in out if not ((x['chap']==150 and x['type']=='竞争联盟') or (x['chap']==188 and x['type']=='亲密') or (x['chap']==214 and x['quote']=='不准告诉夏洛特') or (x['chap']==224 and '埃莉诺' in x['persons'] and x['type']=='承诺') or (x['chap']==225 and x['type']=='亲密') or (x['chap']==286 and x['type']=='亲密') or (x['chap']==315 and '夏洛特' in x['persons']))]
for x in out:
    if x['chap']==203: x['boundary']='被迫边界转折；同意有限且附条件'
    elif x['chap']==179 and x['type']=='婚配': x['boundary']='单方婚配提议，尚未落实'
    elif x['chap']==184: x['boundary']='确定恋人关系；牺牲营救'
    elif x['chap']==271: x['boundary']='神祇附体；为既有恋情背书'
    elif x['chap']==277 or x['chap'] in (335,336,337): x['boundary']='群像竞争；挑战或玩笑，非婚配'
    elif x['chap']==286 and x['type']=='婚配': x['boundary']='政治婚配计划，尚未落实'
    elif x['chap']==229 and x['type']=='婚配': x['boundary']='婚配承诺，尚未落实'
    elif x['chap']==316: x['boundary']='明确未婚夫／未婚妻身份'
    elif x['chap']==125: x['boundary']='恋人关系明确；自愿告别亲吻'
    elif x['chap']==308: x['boundary']='双方亲密关系确立；非婚配'
    elif x['chap']==245: x['boundary']='单方主动；非婚配'
    elif x['chap']==247: x['boundary']='非婚配；再次会面约定'
    elif x['chap']==295: x['boundary']='明确支持承诺；非婚配'
    elif x['chap']==298: x['boundary']='非婚配；邀请对方脱离原阵营'
    elif x['chap']==150: x['boundary']='恋人关系确定；私密边界由埃莉诺设定'
    elif x['chap']==125 and '夏洛特' in x['persons']: x['boundary']='姐弟式玩笑；非婚配'
    elif x['chap']==172 and '蜜丝缇' in x['persons']: x['boundary']='关系未明；蜜丝缇暗中协助救援'
    elif x['chap']==177 and '夏洛特' in x['persons']: x['boundary']='姐弟式亲昵与竞争；非婚配'
    elif x['chap']==184 and x['type']=='群像': x['boundary']='牵挂群像；未作关系承诺'
    elif x['chap']==208 and '爱丽丝塞尔' in x['persons']: x['boundary']='恋人关系已推进；惩罚约定带调情性质'
    elif x['chap']==223 and '爱丽丝塞尔' in x['persons']: x['boundary']='恋人关系确定；三方竞争/质问'
    elif x['chap']==224: x['boundary']='单方索求；恋情未确认'
    elif x['chap']==225 and '爱丽丝塞尔' in x['persons']: x['boundary']='恋人竞争；埃莉诺单方戒备'
    elif x['chap']==229 and x['type']=='亲密': x['boundary']='主动亲吻；恋人关系已推进'
    elif x['chap']==314: x['boundary']='恋爱关系；主动亲密推进'
    elif '玩笑' in x.get('boundary',''): x['boundary']='玩笑／戏称，非婚配'
    elif '附体' in x.get('boundary',''): x['boundary']='神祇附体，不作恋爱确认'
    elif '确定关系' in x.get('boundary',''): x['boundary']='确定恋人关系'
    s=x['scene'].rstrip('。；')
    if len(s)>70: s=s[:69]+'…'
    x['scene']=s
with open(dst,'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False,indent=2)
b=json.load(open(dst,encoding='utf-8'))
assert len(b)==len(out) and all(all(k in x for k in ['chap','chapterTitle','persons','type','place','scene','quote','boundary','globalLine','quoteCheck','reviewFile','reviewNote']) for x in b)
assert all(x['quoteCheck']=='ok' and x['globalLine'] is not None and len(x['scene'])<=70 for x in b)
print('count',len(b))
