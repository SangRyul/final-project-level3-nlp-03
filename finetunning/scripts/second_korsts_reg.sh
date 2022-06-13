#python train_finetunning.py --lr 2e-5 \
#              --model_name klue/bert-base \
#              --num_train_epochs 5 \
#              --config_path ./configs/first_korSTS_reg.yaml \
#              --save_steps 500

python train_finetunning.py --lr 2e-5 \
              --model_name /opt/ml/projects/final-project-level3-nlp-03/finetunning/results/klue-bert-base-korSTS_nli \
              --num_train_epochs 5 \
              --config_path ./configs/first_korSTS_reg.yaml \
              --save_steps 500