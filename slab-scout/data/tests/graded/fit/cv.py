import json, numpy as np
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.linear_model import Ridge
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
a=[x for f in ('part1.json','part2.json') for x in json.load(open(f)) if x[2]!='ERR']
y=np.array([x[1] for x in a],float)
def feat(x):
    n=lambda v:0 if v is None else v
    return [n(x[3]),n(x[7]),n(x[9]),n(x[11]),n(x[12]),n(x[13]),n(x[14]),n(x[15]),n(x[16]),np.log1p(n(x[17])),n(x[18])/1000,n(x[19])/1000,
            n(x[20]),n(x[21]),n(x[22])/100,x[23],x[24],x[25]=='full_art',x[25]=='vintage',x[26] in('pokemon','mtg','yugioh'),n(x[4]),n(x[5]),n(x[6])]
X=np.array([feat(x) for x in a],float)
kf=KFold(5,shuffle=True,random_state=0)
print('n',len(y),'const-median MAE',np.mean(abs(y-np.median(y))).round(2),'current est MAE',np.mean(abs(y-np.array([x[2] for x in a]))).round(2))
for name,m in [('ridge',Ridge(10)),('rf',RandomForestRegressor(200,min_samples_leaf=5,random_state=0)),('gb',GradientBoostingRegressor(n_estimators=100,max_depth=2,learning_rate=0.05,subsample=0.8,random_state=0))]:
    ps=[]
    for seed in range(5):
        p=cross_val_predict(m,X,y,cv=KFold(5,shuffle=True,random_state=seed)); ps.append(np.mean(abs(y-p)))
    # cv-median baseline per fold
    print(name,'CV MAE',np.round(np.mean(ps),2))
bs=[]
for seed in range(5):
    e=[]
    for tr,te in KFold(5,shuffle=True,random_state=seed).split(X):
        e+=list(abs(y[te]-np.median(y[tr])))
    bs.append(np.mean(e))
print('median baseline CV',round(np.mean(bs),2))
rf=RandomForestRegressor(300,min_samples_leaf=5,random_state=0).fit(X,y)
names='cen wearC plain chips scr spk stn crease flat sharp px refpx dmg scuff scrmm slab recut full vint tcg co ed su'.split()
print(sorted(zip(rf.feature_importances_.round(3),names),reverse=True)[:10])
