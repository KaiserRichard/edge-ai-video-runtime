/* Offline canvas renderer; NOT uPlot. Only used when the pinned CDN fails. */
"use strict";
window.LocalCanvasPlot = class {
  constructor(options,data,node) {
    this.options=options;this.data=data;this.node=node;this.xRange=null;
    this.root=document.createElement("div");this.root.className="local-plot";
    this.canvas=document.createElement("canvas");this.root.append(this.canvas);
    this.legend=document.createElement("div");this.legend.className="local-legend";this.root.append(this.legend);node.append(this.root);
    options.series.slice(1).forEach(s=>{const item=document.createElement("button");item.textContent=s.label;item.style.color=s.stroke;item.type="button";item.title="Toggle series";item.onclick=()=>{s.hidden=!s.hidden;item.style.opacity=s.hidden?.35:1;this.draw();};this.legend.append(item);});
    this.canvas.addEventListener("mousemove",ev=>{
      const rect=this.canvas.getBoundingClientRect(),fraction=(ev.clientX-rect.left-40)/(rect.width-78),xs=this.data[0]||[];
      if(!xs.length)return;
      const [min,max]=this.xRange||[xs[0],xs.at(-1)],at=min+fraction*(max-min);
      let index=0;for(let i=1;i<xs.length;i++)if(Math.abs(xs[i]-at)<Math.abs(xs[index]-at))index=i;
      this.canvas.title=`${xs[index].toFixed(2)} ${options.xunit??(options.hist?"ms":"s")} · `+options.series.slice(1).map((s,i)=>`${s.label}: ${Number.isFinite(this.data[i+1]?.[index])?this.data[i+1][index].toFixed(2):"—"}`).join(" · ");
    });this.setSize(options);
  }
  setSize({width,height}) {this.width=width;this.height=height;this.draw();}
  setData(data) {this.data=data;this.draw();}
  setScale(name,range) {if(name==="x")this.xRange=[range.min,range.max];this.draw();}
  destroy() {this.root.remove();}
  draw() {
    const w=this.width,h=this.height-24;if(!w||h<=0)return;
    const dpr=window.devicePixelRatio||1,c=this.canvas;c.style.width=w+"px";c.style.height=h+"px";c.width=w*dpr;c.height=h*dpr;
    const ctx=c.getContext("2d");ctx.scale(dpr,dpr);ctx.font="10px Consolas, monospace";
    const left=40,right=w-38,top=8,bottom=h-24,data=this.data,xs=data[0]||[],series=this.options.series.slice(1);
    let [xmin,xmax]=this.xRange||[xs[0]??0,xs.at(-1)??10];if(xmin===xmax)xmax=xmin+1;
    const range=scale=>{
      const values=series.flatMap((s,i)=>(s.scale||"y")===scale&&!s.hidden?(data[i+1]||[]).filter(Number.isFinite):[]);
      const fixed=this.options.scales[scale]?.range;if(fixed)return fixed();
      let min=0,max=1;for(const value of values){min=Math.min(min,value);max=Math.max(max,value);}return [min,max+(max-min)*.08];
    };
    const yr=range("y"),rr=range("right"),px=x=>left+(x-xmin)/(xmax-xmin)*(right-left),py=(y,r)=>bottom-(y-r[0])/(r[1]-r[0])*(bottom-top);
    ctx.lineWidth=1;
    for(let i=0;i<=4;i++) {
      const y=top+(bottom-top)*i/4,x=left+(right-left)*i/4;
      ctx.strokeStyle=this.options.axes[1].grid.stroke;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,bottom);ctx.stroke();
      ctx.fillStyle=this.options.axes[1].stroke;const val=yr[1]-(yr[1]-yr[0])*i/4;ctx.fillText(Math.abs(val)>=100?val.toFixed(0):val.toFixed(1),0,y+3);
      const tick=xmin+(xmax-xmin)*i/4;
      const tickLabel=this.options.xunit!==undefined?String(Number(tick.toFixed(2))):tick.toFixed(0);
      ctx.fillText(tickLabel+(this.options.xunit!==undefined?"":this.options.hist?"":"s"),x-7,bottom+17);
      if(series.some(s=>s.scale==="right"))ctx.fillText((rr[1]-(rr[1]-rr[0])*i/4).toFixed(0),right+5,y+3);
    }
    ctx.save();ctx.beginPath();ctx.rect(left,top,right-left,bottom-top);ctx.clip();
    series.forEach((s,index)=>{
      if(s.hidden)return;
      const values=data[index+1]||[],r=s.scale==="right"?rr:yr;
      ctx.strokeStyle=s.stroke;ctx.fillStyle=s.stroke;ctx.lineWidth=1.5;ctx.setLineDash(s.dash||[]);
      if(this.options.hist) {
        const bin=(right-left)/Math.max(1,xs.length),bar=bin*.8/series.length;
        values.forEach((y,i)=>{if(!Number.isFinite(y))return;ctx.globalAlpha=.8;ctx.fillRect(px(xs[i])-bin*.4+index*bar,py(y,r),Math.max(1,bar-.5),bottom-py(y,r));});ctx.globalAlpha=1;
      } else if(s.points?.show&&!this.options.stepped) {
        values.forEach((y,i)=>{if(Number.isFinite(y)){ctx.beginPath();ctx.arc(px(xs[i]),py(y,r),2,0,Math.PI*2);ctx.fill();}});
      } else {
        ctx.beginPath();let active=false,previousY=0;
        values.forEach((y,i)=>{if(!Number.isFinite(y)){active=false;return;}const x=px(xs[i]),point=py(y,r);if(active){if(this.options.stepped)ctx.lineTo(x,previousY);ctx.lineTo(x,point);}else ctx.moveTo(x,point);active=true;previousY=point;});ctx.stroke();
        if(s.points?.show)values.forEach((y,i)=>{if(Number.isFinite(y)){ctx.beginPath();ctx.arc(px(xs[i]),py(y,r),2.5,0,Math.PI*2);ctx.fill();}});
      }
    });ctx.restore();
    if(!series.some((s,i)=>(data[i+1]||[]).some(Number.isFinite))){ctx.fillStyle=this.options.axes[1].stroke;ctx.fillText("No observations in this window",left+14,top+30);}
  }
};
