let N=40000
let NUMTRIALS=30  #POSITION1
modernfreq=".75"
let numleaves=24
LL="1e6"
muu="4e-9"
numsamples=2000
epsilon=0.001  ###0.001 guarantees exact rejection sampling.

rm -f -r TrueResults
mkdir TrueResults
 
for ss in 0.01 0.0075 0.005 0.0025
do

python3.9 getH12.py $ss $numleaves

max_parallel_processes=30

for (( c=0; c<${NUMTRIALS}; c++ ))
do 
{
taj=$(head -n 1 TrueResults/H12_${c}.txt)

echo $taj
python3.9 RejectionH12.py $N $numleaves $ss $NUMTRIALS $LL $muu $numsamples $taj $epsilon $c
} &

done

wait
Rscript plotAllResultsH12.R $ss


done


Rscript DEBUGH12.R

