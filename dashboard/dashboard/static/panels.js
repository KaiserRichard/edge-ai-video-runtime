/* Shared uPlot 1.6.31 / local canvas factory for dashboard and lessons. */
"use strict";
window.EdgePanels = {
  create(options, data, node) {
    return new (window.uPlot || window.LocalCanvasPlot)(options, data, node);
  },
  plot(node, initialSpec) {
    const controller = {spec:initialSpec, plot:null, resize:null};
    const options = () => {
      const css=getComputedStyle(document.body),color=key=>css.getPropertyValue("--"+key).trim();
      const spec=controller.spec,colors=(spec.colors||["cyan","purple","amber","blue","pink"]).map(color);
      const axis={stroke:color("muted"),font:"11px system-ui",grid:{stroke:color("grid")},ticks:{stroke:color("grid")},size:48};
      return {
        width:Math.max(100,node.clientWidth),height:node.clientHeight||230,
        hist:!!spec.hist,xunit:spec.xunit,stepped:!!spec.stepped,
        scales:{x:{time:false},y:{auto:true,...(spec.range?{range:()=>spec.range}:{})}},
        legend:{live:true},
        axes:[{...axis,size:32,values:(_,ticks)=>ticks.map(v=>Number(v.toFixed(2)))},axis],
        series:[{label:spec.xunit||"s"},...spec.labels.map((label,i)=>({
          label,stroke:colors[i%colors.length],width:1.8,
          points:{show:!!spec.dots||!!spec.stepped||!!spec.marker&&i===1,size:6},
          ...(spec.dots||spec.marker&&i===1?{paths:()=>null}:{}),
          ...(spec.stepped&&window.uPlot?{paths:uPlot.paths.stepped({align:1})}:{}),
          ...(spec.hist&&window.uPlot?{paths:uPlot.paths.bars({size:[.75,35]}),fill:colors[i%colors.length]+"55"}:{})
        }))]
      };
    };
    const build=()=>{
      controller.plot?.destroy();
      controller.plot=this.create(options(),[controller.spec.x,...controller.spec.ys],node);
    };
    controller.setData=data=>{
      controller.spec={...controller.spec,x:data[0],ys:data.slice(1)};
      controller.plot.setData(data);
    };
    const recolor=()=>{
      if(!node.isConnected){controller.destroy();return;}
      build();
    };
    controller.destroy=()=>{
      controller.resize.disconnect();controller.plot.destroy();
      document.removeEventListener("edge-theme",recolor);
      window.removeEventListener("edge-uplot-ready",recolor);
    };
    controller.resize=new ResizeObserver(()=>{
      if(node.clientWidth)controller.plot.setSize({width:node.clientWidth,height:node.clientHeight||230});
    });
    build();controller.resize.observe(node);
    document.addEventListener("edge-theme",recolor);
    window.addEventListener("edge-uplot-ready",recolor);
    node._edgePanel=controller;
    return controller;
  }
};
