#include "sierrachart.h"
#include "../Lukacino_OpenX_Range_RRR.cpp"
#include <cstdlib>
int main(int argc,char**argv){
  static SCStudyInterface sc; sc.SetDefaults=1; scsf_Lukacino_OpenX_Range_RRR(sc); sc.SetDefaults=0;
  // argv: file then pairs idx=value
  FILE*f=fopen(argv[1],"r"); int d,t; float o,h,l,c; int nlim = getenv("NBARS")?atoi(getenv("NBARS")):1<<30;
  while(fscanf(f,"%d,%d,%f,%f,%f,%f",&d,&t,&o,&h,&l,&c)==6 && (int)sc.Close.v.size()<nlim){sc.BaseDateTimeIn.v.push_back({d,t});sc.Open.v.push_back(o);sc.High.v.push_back(h);sc.Low.v.push_back(l);sc.Close.v.push_back(c);}
  for(int k=2;k<argc;k++){int idx;double v; sscanf(argv[k],"%d=%lf",&idx,&v); sc.Input[idx].v=v;}
  int N=sc.Close.v.size(); int warm = getenv("WARM")?atoi(getenv("WARM")):0;
  // 1) úplný přepočet prvních WARM barů (graf načten), 2) replay po barech
  sc.IsFullRecalculation=1; sc.ArraySize=warm;
  for(int i=0;i<warm;i++){sc.Index=i;scsf_Lukacino_OpenX_Range_RRR(sc);}
  sc.IsFullRecalculation=0;
  for(int i=warm;i<N;i++){ sc.ArraySize=i+1; if(i>0){sc.Index=i-1;scsf_Lukacino_OpenX_Range_RRR(sc);} sc.Index=i; sc.bracket(i); scsf_Lukacino_OpenX_Range_RRR(sc);}
  printf("alerts %d logs %d errors %d trades %zu\n",sc.alerts,sc.logs,sc.errors,sc.trades.size());
  FILE*g=fopen(getenv("OUT")?getenv("OUT"):"trades.csv","w"); fprintf(g,"d,t,dir,entry,exit,xd,xt,why\n");
  for(auto&x:sc.trades) fprintf(g,"%d,%d,%d,%.2f,%.2f,%d,%d,%c\n",x.d,x.t,x.dir,x.e,x.x,x.xd,x.xt,x.why);
}
