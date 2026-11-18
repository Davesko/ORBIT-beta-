/* Dark Workshop presentation layer. No native mutations, job creation or routing rules. */
const AtelierArt = {
  root:'assets/workshop/',
  assets:{
    'agent-astronaut':[1086,1448,61,121,965,1238],
    'agent-dragon':[1122,1402,89,110,944,1235],
    'agent-fox':[1196,1315,155,85,886,1171],
    'agent-goblin':[1122,1402,175,116,772,1191],
    'agent-hacker':[1086,1448,209,114,668,1261],
    'agent-jellyfish':[1122,1402,70,149,983,1142],
    'agent-robot':[1196,1315,214,60,768,1200],
    'agent-samurai':[1122,1402,218,173,689,1146],
    'agent-wizard':[1122,1402,134,44,856,1321],
    'bookshelf':[1052,1495,160,84,731,1348],
    'desk-editing':[1774,887,102,95,1570,703],
    'desk-research':[1484,1060,100,137,1287,827]
  },
  image(name,x,y,w,h,cls='') {
    const [iw,ih,bx,by,bw,bh]=this.assets[name];
    return `<svg class="${cls}" x="${x}" y="${y}" width="${w}" height="${h}" viewBox="${bx} ${by} ${bw} ${bh}" preserveAspectRatio="xMidYMid meet" style="width:${w}px!important;height:${h}px!important;min-height:0!important;max-height:none" overflow="hidden" aria-hidden="true" pointer-events="none"><image href="${this.root+name}.png" width="${iw}" height="${ih}" image-rendering="pixelated"/></svg>`;
  },
  sprite(type) {
    return ({goblin:'agent-goblin',robot:'agent-robot',wizard:'agent-wizard',cyberfox:'agent-fox',hacker:'agent-hacker',astronaut:'agent-astronaut',samurai:'agent-samurai',jellyfish:'agent-jellyfish',dragon:'agent-dragon'})[type];
  }
};
