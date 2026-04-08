wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh 

#Or
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-aarch64.sh


bash ~/Miniconda3-latest-Linux-aarch64.sh

#create a new conda environment
conda create -n cn python=3.11



#activate your conda environment
conda activate cn


#ALTERNATIVA CON VENV
python3 -m venv venv
source venv/bin/activate
# If you want to install containernet in "edit" mode
pip install -e . --no-binary :all:
# If you want to install containernet in "normal" mode


#move to containernet directory

cd ~/containernet

#install python dependencies
pip install .

#Play an example
#Note using python VENV or Conda we must specify the python3 path if we need to run it as with sudo privileges, otherwise it not works because we cannot reach the correct python executable and our packages directory
cd containernet/
sudo -E env PATH=$PATH python3 examples/containernet_example.py

#INSTALL FRR for routing
git clone https://github.com/frrouting/frr.git frr
cd frr

./docker/alpine/build.sh