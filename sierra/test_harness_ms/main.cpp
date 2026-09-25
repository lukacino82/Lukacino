// Emulace: úplný přepočet prvních WARM barů (graf načten), pak Replay bar po baru.
// ./ms bars.csv [index=hodnota ...]   env: WARM, NBARS, OUT (virtuální obchody), FILLS (fills brokera)
#include "sierrachart.h"
#include "../Lukacino_MultiSystem.cpp"
#include <cstdlib>
int main(int argc,char**argv){
  static SCStudyInterface sc; sc.SetDefaults=1; scsf_Lukacino_MultiSystem(sc); sc.SetDefaults=0;
  FILE*f=fopen(argv[1],"r"); int d,t; float o,h,l,c,v,b,a; long nlim = getenv("NBARS")?atol(getenv("NBARS")):1L<<40;
  while(fscanf(f,"%d,%d,%f,%f,%f,%f,%f,%f,%f",&d,&t,&o,&h,&l,&c,&v,&b,&a)==9 && (long)sc.Close.v.size()<nlim){
    sc.BaseDateTimeIn.v.push_back({d,t}); sc.Open.v.push_back(o); sc.High.v.push_back(h); sc.Low.v.push_back(l); sc.Close.v.push_back(c);
    sc.Volume.v.push_back(v); sc.BidVolume.v.push_back(b); sc.AskVolume.v.push_back(a);}
  for(int k=2;k<argc;k++){int idx;double val; if(sscanf(argv[k],"%d=%lf",&idx,&val)==2) sc.Input[idx].v=val;}
  int N=sc.Close.v.size(); int warm = getenv("WARM")?atoi(getenv("WARM")):0;
  sc.IsFullRecalculation=1; sc.ArraySize=warm;
  for(int i=0;i<warm;i++){sc.Index=i; sc.IndexOfLastVisibleBar=i; scsf_Lukacino_MultiSystem(sc);}
  sc.IsFullRecalculation=0;
  for(int i=warm;i<N;i++){ sc.ArraySize=i+1; sc.IndexOfLastVisibleBar=i; sc.IndexOfFirstVisibleBar=std::max(0,i-500);
    if(i>0){sc.Index=i-1; scsf_Lukacino_MultiSystem(sc);}
    sc.checkStops(i); sc.Index=i; scsf_Lukacino_MultiSystem(sc);}
  { State* st=(State*)sc.pp[1]; if(st) printf("dni rozhodnuto %zu, prvni %d, posledni %d\n", st->C.size(), st->Date.empty()?0:st->Date.front(), st->Date.empty()?0:st->Date.back()); }
  sc.LastCallToFunction=1; std::string panel=sc.lastPanel; scsf_Lukacino_MultiSystem(sc);
  printf("virt. obchodů %zu | fills %zu | pozice %d | broker realized %.1f b. | rejects %d | alerts %d | errors %d\n",
         sc.trades.size(), sc.fills.size(), sc.pos, sc.realized, sc.rejects, sc.alerts, sc.errors);
  if(getenv("PANEL")) printf("%s\n", panel.c_str());
  FILE*g=fopen(getenv("OUT")?getenv("OUT"):"ms_trades.txt","w"); for(auto&s:sc.trades) fprintf(g,"%s\n",s.c_str()); fclose(g);
  FILE*q=fopen(getenv("FILLS")?getenv("FILLS"):"ms_fills.csv","w"); fprintf(q,"d,t,side,qty,px,tag\n");
  for(auto&x:sc.fills) fprintf(q,"%d,%d,%d,%d,%.2f,%s\n",x.d,x.t,x.side,x.qty,x.px,x.tag.c_str()); fclose(q);
}
