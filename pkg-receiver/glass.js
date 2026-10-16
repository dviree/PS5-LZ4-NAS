/* Images tab: one card per game with a choice of its images (the original
   exFAT / FFPFSC and the LZ4 copy's exFAT image), from the catalog's game and
   variant fields. Lines are joined without newlines: end every statement
   with ; and use no line comments. */
function groupImgs(list){var by={},out=[];
list.forEach(function(g){var k=g.game;if(!k){out.push({one:g});return;}
if(!by[k]){by[k]={vars:[]};out.push(by[k]);}by[k].vars.push(g);});
return out.map(function(x){if(x.one)return x.one;if(x.vars.length===1)return x.vars[0];
x.vars.sort(function(a,b){return (a.variant==='LZ4')-(b.variant==='LZ4');});
return {group:1,vars:x.vars,title:x.vars[0].title.replace(/ \(LZ4\)$/,'')};});}
function imgCard(x){var d=document.createElement('div');d.className='card';var sel=0;
var lead=x.vars.filter(function(v){return v.hasIcon;})[0];
var cov=lead?'<img class='+covCls(lead)+' src=http://'+pcEl.value+':9898/icon/'+encodeURIComponent(lead.id)+'>':'<div class=\"cov cov5\"><span>'+imgIcon(x.vars[0].format)+'</span></div>';
d.innerHTML=cov+'<div class=t>'+esc(x.title)+'</div><div class=vsel></div><div class=m></div>';
var vs=d.querySelector('.vsel'),m=d.querySelector('.m');
function pick(i){sel=i;var bs=vs.children;for(var k=0;k<bs.length;k++)bs[k].className=k===i?'on':'';var v=x.vars[i];
m.innerHTML='<span class=vfmt style=background:'+fmtColor(v.format)+'>'+esc((v.format||'img').toUpperCase())+'</span> &middot; '+esc(v.sizeText||'');}
x.vars.forEach(function(v,i){var b=document.createElement('button');b.textContent=v.variant||v.format;b.onclick=function(ev){ev.stopPropagation();pick(i);};vs.appendChild(b);});
pick(0);
var cb=document.createElement('button');cb.textContent='Copy to homebrew';
cb.onclick=function(ev){ev.stopPropagation();var v=x.vars[sel];copyImg(v.id,v.file||v.title,v.size||0);};
d.appendChild(cb);return d;}
/* Stay awake: a switch in the header for awake.c (on unless switched off). */
;(function(){var hd=document.querySelector('.hd');if(!hd)return;
var b=document.createElement('button');b.id='awake';b.textContent='Stay awake';
hd.insertBefore(b,document.getElementById('pcstat'));
function show(j){b.className=j.always?'on':'';b.textContent=j.always?'☀ Stay awake: on':'☾ Stay awake: off';
b.title=j.always?'The PS5 never goes to rest mode while this runs':'The PS5 stays awake only while it installs or copies';}
fetch('/api/keep-awake').then(function(r){return r.json();}).then(show).catch(function(){b.style.display='none';});
b.onclick=function(){fetch('/api/keep-awake?always='+(b.className==='on'?0:1)).then(function(r){return r.json();}).then(show);};})();
