// Block Runner — UK city generator.
// Pure function: buildCity() returns the road network, blocks (faces between roads), pavements,
// building lots and park features. Deterministic (own seeded RNG), no three.js needed, so it can be
// previewed in node and dropped into the game unchanged.
// Coordinates: x east, z south (same as the game and the minimap). Traffic drives on the LEFT.
(function(root){
'use strict';
function rng(seed){let a=seed>>>0;return()=>{a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}
const hyp=Math.hypot;
function lerp(a,b,t){return a+(b-a)*t;}
// Catmull-Rom through points, sampled every ~step metres
function spline(P,step){const out=[P[0]];for(let i=0;i<P.length-1;i++){const p0=P[Math.max(0,i-1)],p1=P[i],p2=P[i+1],p3=P[Math.min(P.length-1,i+2)];
  const n=Math.max(1,Math.ceil(hyp(p2[0]-p1[0],p2[1]-p1[1])/step));
  for(let k=1;k<=n;k++){const t=k/n,t2=t*t,t3=t2*t;const f=(a,b,c,d)=>.5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t2+(-a+3*b-3*c+d)*t3);out.push([f(p0[0],p1[0],p2[0],p3[0]),f(p0[1],p1[1],p2[1],p3[1])]);}}
  return out;}
function polyLen(P){let L=0;for(let i=1;i<P.length;i++)L+=hyp(P[i][0]-P[i-1][0],P[i][1]-P[i-1][1]);return L;}
function area(P){let a=0;for(let i=0;i<P.length;i++){const p=P[i],q=P[(i+1)%P.length];a+=p[0]*q[1]-q[0]*p[1];}return a/2;}
function inside(P,x,z){let c=false;for(let i=0,j=P.length-1;i<P.length;j=i++){const a=P[i],b=P[j];if((a[1]>z)!==(b[1]>z)&&x<(b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0])c=!c;}return c;}
function segDist(px,pz,a,b){const dx=b[0]-a[0],dz=b[1]-a[1],l=dx*dx+dz*dz||1;const t=Math.max(0,Math.min(1,((px-a[0])*dx+(pz-a[1])*dz)/l));return hyp(px-a[0]-dx*t,pz-a[1]-dz*t);}
function resample(P,step,closed){const out=[];const n=P.length,m=closed?n:n-1;let carry=0;
  for(let i=0;i<m;i++){const a=P[i],b=P[(i+1)%n],L=hyp(b[0]-a[0],b[1]-a[1]);let t=carry;while(t<L){out.push([lerp(a[0],b[0],t/L),lerp(a[1],b[1],t/L)]);t+=step;}carry=t-L;}
  if(!closed)out.push(P[n-1]);return out;}
function polyDist(P,x,z,closed){let d=1e9;const n=P.length;for(let i=0;i<(closed?n:n-1);i++)d=Math.min(d,segDist(x,z,P[i],P[(i+1)%n]));return d;}
// oriented box corners
function obb(cx,cz,w,d,a){const c=Math.cos(a),s=Math.sin(a),ux=c*w/2,uz=-s*w/2,vx=s*d/2,vz=c*d/2;return[[cx-ux-vx,cz-uz-vz],[cx+ux-vx,cz+uz-vz],[cx+ux+vx,cz+uz+vz],[cx-ux+vx,cz-uz+vz]];}
function obbOverlap(A,B){for(const P of[A,B])for(let i=0;i<4;i++){const p=P[i],q=P[(i+1)%4],nx=q[1]-p[1],nz=p[0]-q[0];
  let a0=1e9,a1=-1e9,b0=1e9,b1=-1e9;for(const v of A){const t=v[0]*nx+v[1]*nz;a0=Math.min(a0,t);a1=Math.max(a1,t);}for(const v of B){const t=v[0]*nx+v[1]*nz;b0=Math.min(b0,t);b1=Math.max(b1,t);}
  if(a1<=b0||b1<=a0)return false;}return true;}

// ------------------------------------------------------------------ the street plan
// Districts: 'centre' high street, 'terrace' Victorian terraces (NW), 'park' (NE), 'estate' tower blocks (SE), 'works' mills and warehouses (SW)
const W=250; // half size of the city
const NODES={
  // perimeter
  NW:[-W,-W], N1:[-125,-W], N2:[-4,-W], N3:[118,-W], NE:[W,-W],
  E1:[W,-128], E2:[W,-12], E3:[W,110], SE:[W,W],
  S3:[150,W], S2:[6,W], S1:[-102,W], SW:[-W,W],
  W3:[-W,132], W2:[-W,18], W1:[-W,-52], W0:[-W,-140],
  // high street and the three big roundabouts
  RW:[-150,16], C:[0,2], RE:[150,-14],
  H1:[-75,12], H2:[88,-6],
  // Church Street (N-S through the centre)
  CN1:[-4,-140], CN2:[-2,-52], CS1:[4,74], CS2:[6,128],
  // terraces (NW): Albert Road and four terraced streets
  A1:[-128,-140], A2:[-134,-52],
  T1w:[-W,-195], T1a:[-127,-196], T1e:[-4,-196],
  // park side (NE)
  PL1:[118,-130],
  // estate (SE)
  M1:[70,104], M2:[160,108], X1:[88,74],
  // works (SW)
  K1:[-102,132], K2:[-128,74],
};
// edges: [from, to, class, via points]; class: 'main' (wide) or 'res' (residential)
const EDGES=[
  // perimeter ring
  ['NW','N1','main',[[-190,-W-6]]],['N1','N2','main',[[-64,-W+5]]],['N2','N3','main',[[56,-W-5]]],['N3','NE','main',[[186,-W+4]]],
  ['NE','E1','main',[[W+6,-190]]],['E1','E2','main',[[W-5,-70]]],['E2','E3','main',[[W+5,50]]],['E3','SE','main',[[W-6,180]]],
  ['SE','S3','main',[[200,W+5]]],['S3','S2','main',[[78,W-6]]],['S2','S1','main',[[-48,W+5]]],['S1','SW','main',[[-176,W-5]]],
  ['SW','W3','main',[[-W+5,190]]],['W3','W2','main',[[-W-5,75]]],['W2','W1','main',[[-W+4,-18]]],['W1','W0','main',[[-W-4,-96]]],['W0','T1w','main'],['T1w','NW','main'],
  // high street: west approach, RW, H1, C, H2, RE, east approach
  ['W2','RW','main',[[-200,20]]],['RW','H1','high',[[-112,17]]],['H1','C','high',[[-38,4]]],['C','H2','high',[[44,0]]],['H2','RE','high',[[120,-12]]],['RE','E2','main',[[200,-16]]],
  // Church Street
  ['N2','T1e','res'],['T1e','CN1','res'],['CN1','CN2','res'],['CN2','C','high'],['C','CS1','high',[[2,38]]],['CS1','CS2','main'],['CS2','S2','main'],
  // Albert Road (gently curving N-S through the terraces) down to RW
  ['N1','T1a','res'],['T1a','A1','res',[[-131,-168]]],['A1','A2','res',[[-137,-96]]],['A2','RW','main',[[-144,-20]]],
  // terraced streets (E-W), each with a slight bend
  ['T1w','T1a','res',[[-190,-192]]],['T1a','T1e','res',[[-66,-200]]],
  ['W0','A1','res',[[-190,-146]]],['A1','CN1','res',[[-66,-136]]],
  ['W1','A2','res',[[-192,-48]]],['A2','CN2','res',[[-70,-58]]],
  // NE: Park Lane, and the crescent
  ['N3','PL1','res',[[121,-190]]],['PL1','RE','main',[[132,-70]]],['PL1','E1','res',[[184,-150]]],
  // SE estate: Station Road, Meadow Way, Tower Crescent
  ['H2','X1','res',[[92,34]]],['X1','M1','res'],['CS1','X1','res',[[46,68]]],
  ['CS2','M1','res',[[38,118]]],['M1','M2','res',[[114,96]]],['M2','E3','res',[[208,112]]],['RE','M2','main',[[168,48]]],
  ['M1','S3','res',[[70,170],[116,206]]],
  // SW works: Canal Street and Mill Road
  ['W3','K1','res',[[-176,138]]],['K1','CS2','res',[[-48,124]]],
  ['RW','K2','main',[[-140,44]]],['K2','K1','res',[[-112,104]]],['K1','S1','res'],['W2','K2','res',[[-190,64]]],
];
const ROUND={RW:13,C:10,RE:13};          // roundabouts: radius of the central island
const WIDTH={main:15,high:15,res:12};             // carriageway width (kerb to kerb)
const PAVE=3.2;                           // pavement width
const LANE_OFF={main:2.6,high:2.6,res:2.2};        // lane centre from the road centreline

function districtAt(x,z){
  if(x<-12&&z<-24)return'terrace';
  if(x>12&&z<-24)return'park';
  if(x>12&&z>30)return'estate';
  if(x<-12&&z>30)return'works';
  return'centre';}

function buildCity(seed){
  const R=rng(seed||20261127),rf=(a,b)=>a+(b-a)*R();
  // ---- nodes and edges
  const nodes={};for(const k in NODES)nodes[k]={id:k,x:NODES[k][0],z:NODES[k][1],edges:[],rb:ROUND[k]||0};
  const edges=EDGES.map((e,i)=>{const a=nodes[e[0]],b=nodes[e[1]],via=e[3]||[];
    const pts=spline([[a.x,a.z],...via,[b.x,b.z]],4);
    const E={id:i,a:e[0],b:e[1],cls:e[2],w:WIDTH[e[2]],lane:LANE_OFF[e[2]],pts,len:polyLen(pts)};
    a.edges.push(E);b.edges.push(E);return E;});
  // ---- trimmed drivable centreline: stops at the roundabout ring or the junction mouth
  const mouth=n=>n.rb?n.rb+WIDTH.main*.5+1.5:(n.edges.length>2?WIDTH.main*.5+2:0);
  for(const E of edges){const A=nodes[E.a],B=nodes[E.b];E.cut0=Math.min(mouth(A),E.len*.4);E.cut1=Math.min(mouth(B),E.len*.4);}
  // ---- faces (blocks): walk the planar graph keeping the face on the left
  const out=n=>n.edges.map(E=>{const fwd=E.a===n.id,P=E.pts,q=fwd?P[1]:P[P.length-2];return{E,fwd,ang:Math.atan2(q[1]-n.z,q[0]-n.x)};}).sort((p,q)=>p.ang-q.ang);
  const used=new Set(),faces=[];
  for(const E of edges)for(const fwd of[true,false]){const key=E.id+(fwd?'f':'r');if(used.has(key))continue;
    const loop=[];let cur={E,fwd},guard=0;
    while(guard++<200){const k=cur.E.id+(cur.fwd?'f':'r');if(used.has(k))break;used.add(k);loop.push(cur);
      const end=nodes[cur.fwd?cur.E.b:cur.E.a],P=cur.E.pts,prev=cur.fwd?P[P.length-2]:P[1];
      const back=Math.atan2(prev[1]-end.z,prev[0]-end.x),O=out(end);
      // next edge clockwise from the one we came in on (face on the left when turning as tightly right as possible)
      let best=null,bd=1e9;for(const o of O){if(o.E===cur.E&&O.length>1)continue;let d=back-o.ang;while(d<=1e-9)d+=Math.PI*2;if(d<bd){bd=d;best=o;}}
      if(!best)break;cur={E:best.E,fwd:best.fwd};}
    const poly=[];const side=[];for(const s of loop){const P=s.fwd?s.E.pts:s.E.pts.slice().reverse();for(let i=0;i<P.length-1;i++){poly.push(P[i]);side.push(s.E);}}
    const A=area(poly);if(A<=0){if(!faces.outer||A<faces.outer.area)faces.outer={poly,side,area:A,loop};continue;} // the outside of the city
    faces.push({poly,side,area:A,loop});}
  // ---- inset each face: pavement edge (kerb) and building line, using each side's own road width
  function inset(poly,side,extra,outward){const n=poly.length,lines=[];
    for(let i=0;i<n;i++){const p=poly[i],q=poly[(i+1)%n],dx=q[0]-p[0],dz=q[1]-p[1],l=hyp(dx,dz)||1,nx=-dz/l,nz=dx/l,o=side[i].w/2+extra;
      lines.push([[p[0]+nx*o,p[1]+nz*o],[dx/l,dz/l]]);}
    const res=[];for(let i=0;i<n;i++){const [p1,d1]=lines[(i+n-1)%n],[p2,d2]=lines[i];const cr=d1[0]*d2[1]-d1[1]*d2[0];
      if(Math.abs(cr)<1e-3){res.push(p2);continue;}
      const t=((p2[0]-p1[0])*d2[1]-(p2[1]-p1[1])*d2[0])/cr;let x=p1[0]+d1[0]*t,z=p1[1]+d1[1]*t;
      if(hyp(x-p2[0],z-p2[1])>12){x=p2[0];z=p2[1];}res.push([x,z]);}
    // drop points that ended up outside (very sharp corners) and anything inside a roundabout's clearance
    // drop spikes: a proper offset point is at least (half width + extra) from every road of this face
    const own=[...new Set(side)];
    return res.filter(p=>(outward?!inside(poly,p[0],p[1]):inside(poly,p[0],p[1]))&&own.every(E=>polyDist(E.pts,p[0],p[1],false)>=E.w/2+extra-.35));}
  const rbClear=(x,z,m)=>{for(const k in ROUND){const n=nodes[k];if(hyp(x-n.x,z-n.z)<n.rb+WIDTH.main+m)return true;}return false;};
  const blocks=[];
  for(const F of faces){const kerb=inset(F.poly,F.side,0).filter(p=>!rbClear(p[0],p[1],0)),
      line=inset(F.poly,F.side,PAVE).filter(p=>!rbClear(p[0],p[1],PAVE)),
      walk=resample(inset(F.poly,F.side,PAVE*.5).filter(p=>!rbClear(p[0],p[1],PAVE*.5)),5,true);
    if(kerb.length<3||line.length<3||walk.length<4)continue;
    let cx=0,cz=0;for(const p of line){cx+=p[0];cz+=p[1];}cx/=line.length;cz/=line.length;
    const xs=kerb.map(p=>p[0]),zs=kerb.map(p=>p[1]);
    blocks.push({poly:F.poly,kerb,line,walk,edgeIds:new Set(F.side.map(e=>e.id)),cx,cz,district:districtAt(cx,cz),x0:Math.min(...xs),x1:Math.max(...xs),z0:Math.min(...zs),z1:Math.max(...zs),area:Math.abs(area(line))});}
  {const F=faces.outer;const kerb=inset(F.poly,F.side,0,true),line=inset(F.poly,F.side,PAVE,true),walk=resample(inset(F.poly,F.side,PAVE*.5,true),5,true);
    const xs=kerb.map(p=>p[0]),zs=kerb.map(p=>p[1]);
    blocks.push({poly:F.poly,kerb,line,walk,edgeIds:new Set(F.side.map(e=>e.id)),cx:0,cz:0,district:'belt',outer:true,x0:Math.min(...xs),x1:Math.max(...xs),z0:Math.min(...zs),z1:Math.max(...zs),area:0});
    // the edge of the playable city: a wall a little beyond the belt of buildings
    var boundary=inset(F.poly,F.side,PAVE+26,true);}
  // the big park: the NE block west of Park Lane
  let parkB=null;for(const b of blocks)if(b.district==='park'&&(!parkB||b.cx<parkB.cx))parkB=b;if(parkB)parkB.park=true;
  // ---- building lots along each block's building line
  const lots=[];const all=[];
  const KIND={centre:{w:[8,11],d:[11,15],h:[9,16],kind:'shop',gap:0},terrace:{w:[5,6],d:[8,9],h:[7,8],kind:'terrace',gap:0},
    park:{w:[7,9],d:[10,12],h:[10,13],kind:'townhouse',gap:0},estate:{w:[16,20],d:[14,18],h:[30,52],kind:'tower',gap:14},works:{w:[18,30],d:[14,22],h:[8,13],kind:'works',gap:5}};
  for(const b of blocks){if(b.park)continue;const P=b.line,n=P.length;b.lots=[];
    // walk the building line by distance (it is sampled every few metres along curves)
    const cum=[0];for(let i=0;i<n;i++){const p=P[i],q=P[(i+1)%n];cum.push(cum[i]+hyp(q[0]-p[0],q[1]-p[1]));}const per=cum[n];
    const at=s=>{s=((s%per)+per)%per;let i=0;while(i<n-1&&cum[i+1]<s)i++;const p=P[i],q=P[(i+1)%n],L=cum[i+1]-cum[i]||1,t=(s-cum[i])/L;return[lerp(p[0],q[0],t),lerp(p[1],q[1],t)];};
    let s=0;while(s<per-4){const here=at(s),dist0=b.outer?districtAt(here[0]*.7,here[1]*.7):b.district,S=KIND[dist0==='belt'?'works':dist0];
      const w=rf(S.w[0],S.w[1]),d=Math.min(rf(S.d[0],S.d[1]),b.outer?18:99);
      const a0=at(s),a1=at(s+w),dx=a1[0]-a0[0],dz=a1[1]-a0[1],L=hyp(dx,dz);
      if(L<w*.92){s+=1.5;continue;}                                            // a corner: skip on
      const ux=dx/L,uz=dz/L,nx=-uz,nz=ux,ang=Math.atan2(-uz,ux);
      const cx=(a0[0]+a1[0])/2+nx*(d/2+.15),cz=(a0[1]+a1[1])/2+nz*(d/2+.15),box=obb(cx,cz,L,d,ang);
      const ok=box.every(c=>b.outer?(!inside(P,c[0],c[1])&&inside(boundary,c[0],c[1])):inside(P,c[0],c[1]))&&!all.some(o=>obbOverlap(o,box))&&!box.some(c=>rbClear(c[0],c[1],PAVE+1));
      if(ok){const lot={cx,cz,w:L,d,ang,kind:S.kind==='tower'&&b.outer?'works':S.kind,h:rf(S.h[0],S.h[1])*(b.outer&&S.kind==='tower'?.4:1),district:dist0,box,block:blocks.indexOf(b)};lots.push(lot);all.push(box);b.lots.push(lot);s+=w+S.gap;}
      else s+=1.5;}}
  for(const l of lots){const c=Math.cos(l.ang),sn=Math.sin(l.ang),fx=l.cx-sn*l.d/2,fz=l.cz-c*l.d/2;
    let best=null,bd=1e9;for(const E of edges){const dd=polyDist(E.pts,fx,fz,false);if(dd<bd){bd=dd;best=E;}}
    l.front=best.id;if(best.cls==='high'&&bd<best.w/2+PAVE+2){l.kind='shop';l.h=rf(9,13);}}
  // estate blocks: a couple of extra towers set back in the green
  for(const b of blocks){if(b.district!=='estate')continue;for(let k=0;k<4;k++){const w=rf(16,20),d=rf(14,18),a=rf(-.4,.4);const cx=b.cx+rf(-25,25),cz=b.cz+rf(-25,25),box=obb(cx,cz,w,d,a);
    if(box.every(c=>inside(b.line,c[0],c[1])&&polyDist(b.line,c[0],c[1],true)>6)&&!all.some(o=>obbOverlap(o,box))){const lot={cx,cz,w,d,ang:a,kind:'tower',h:rf(34,56),district:'estate',box,block:blocks.indexOf(b)};lots.push(lot);all.push(box);b.lots.push(lot);}}}
  // ---- zebra crossings: on residential and main roads a little way from junctions
  const crossings=[];for(const E of edges){if(E.len<60)continue;const P=E.pts;let acc=0;const at=E.len/2;
    for(let i=1;i<P.length;i++){const s=hyp(P[i][0]-P[i-1][0],P[i][1]-P[i-1][1]);if(acc+s>=at){const t=(at-acc)/s;crossings.push({x:lerp(P[i-1][0],P[i][0],t),z:lerp(P[i-1][1],P[i][1],t),ang:Math.atan2(P[i][1]-P[i-1][1],P[i][0]-P[i-1][0]),w:E.w,edge:E.id});break;}acc+=s;}}
  for(const b of blocks)b.links={};
  for(const X of crossings){const bs=blocks.filter(b=>b.edgeIds.has(X.edge));if(bs.length<2)continue;
    const near=b=>{let k=0,d=1e9;b.walk.forEach((p,i)=>{const q=hyp(p[0]-X.x,p[1]-X.z);if(q<d){d=q;k=i;}});return[k,d];};
    const [ka,da]=near(bs[0]),[kb,db]=near(bs[1]);if(da>X.w||db>X.w)continue;
    const ia=blocks.indexOf(bs[0]),ib=blocks.indexOf(bs[1]);
    (bs[0].links[ka]=bs[0].links[ka]||[]).push({blk:ib,t:kb,x:X.x,z:X.z});(bs[1].links[kb]=bs[1].links[kb]||[]).push({blk:ia,t:ka,x:X.x,z:X.z});X.ok=true;}
  // ---- traffic lanes (drive on the LEFT): one lane each way, trimmed at junction mouths / roundabout rings
  const sub=(P,s0,s1)=>{const out=[];let acc=0;for(let i=0;i<P.length-1;i++){const a=P[i],b=P[i+1],L=hyp(b[0]-a[0],b[1]-a[1]);
      if(acc+L>=s0&&acc<=s1){const t0=Math.max(0,(s0-acc)/L),t1=Math.min(1,(s1-acc)/L);if(!out.length)out.push([lerp(a[0],b[0],t0),lerp(a[1],b[1],t0)]);out.push([lerp(a[0],b[0],t1),lerp(a[1],b[1],t1)]);}acc+=L;}return out;};
  const leftOff=(P,o)=>P.map((p,i)=>{const a=P[Math.max(0,i-1)],b=P[Math.min(P.length-1,i+1)],dx=b[0]-a[0],dz=b[1]-a[1],l=hyp(dx,dz)||1;return[p[0]+dz/l*o,p[1]-dx/l*o];});
  const mkLane=P=>{const cum=[0];for(let i=1;i<P.length;i++)cum.push(cum[i-1]+hyp(P[i][0]-P[i-1][0],P[i][1]-P[i-1][1]));return{pts:P,cum,len:cum[cum.length-1]};};
  for(const E of edges){const c=sub(E.pts,E.cut0,E.len-E.cut1);E.lanes={'1':mkLane(leftOff(c,E.lane)),'-1':mkLane(leftOff(c.slice().reverse(),E.lane))};
    E.kerbOff=E.w/2-1.35;}
  for(const k in nodes){const n=nodes[k];n.outs=n.edges.map(E=>({E,dir:E.a===k?1:-1}));}
  return{nodes,edges,blocks,lots,crossings,boundary,ROUND,WIDTH,PAVE,LANE_OFF,size:W,helpers:{inside,polyDist,obb,obbOverlap,area,spline,resample}};}
root.buildCity=buildCity;
if(typeof module!=='undefined')module.exports={buildCity};
})(typeof window!=='undefined'?window:globalThis);
