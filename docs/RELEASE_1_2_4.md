# CinePulse 1.2.4

CinePulse 1.2.4 muda a prioridade operacional do runtime: em vez de medir headroom para reduzir trabalho antes de um problema acontecer, o render começa no envelope máximo suportado pela estrutura atual do pipeline e só recua depois de uma falha concreta.

## CPU

Todos os perfis de máquina passam a disponibilizar todos os threads lógicos ao render. As opções de perfil continuam aceitas para compatibilidade de projeto/UI, mas deixam de reservar threads para o desktop durante o processamento.

## Real-ESRGAN

A concorrência deixa de ser reduzida por VRAM livre ou geometria da fonte.

- adaptadores com 20 GB+ usam até 4 processos GPU;
- adaptadores com 7,5 GB+ usam até 3 processos GPU;
- adaptadores com 4 GB+ usam até 2 processos GPU;
- load/save usa até 4 workers do host;
- uma falha/OOM real continua autorizando retry/fallback em menor pressão.

## RAM, scratch e overlap

O planner neural usa budgets fixos máximos em vez de derivá-los de telemetria de headroom:

- Real-ESRGAN: workset de 16 GiB, até 3 worksets simultâneos, extract overlap e pack overlap ativos;
- RIFE: workset de 12 GiB, até 2 worksets simultâneos e extract overlap ativo;
- velocidade de scratch, RAM disponível e VRAM livre deixam de diminuir preventivamente esses envelopes.

Checagens de capacidade necessárias para impedir saída impossível/corrompida continuam separadas da política de desempenho.

## Runtime adaptativo

O controlador adaptativo permanece na API para compatibilidade, porém suas amostras não reduzem CPU, chunks nem overlap em 1.2.4. RAM%, VRAM livre, temperatura, throughput e eventos de instabilidade medidos não causam throttling preventivo.

## RIFE

RIFE passa a começar com uma política agressiva fixa sem gating por VRAM livre:

- abaixo de UHD: 3:3:3;
- UHD: 2:2:2;
- se a execução realmente falhar/OOM, o runner tenta o fallback conservador já existente;
- integridade dos PNGs e contagem/dimensões continuam sendo verificadas antes da promoção da saída.

## O que não foi removido

Esta release não desliga mecanismos que protegem correção do resultado. AtomicOutput, validação de mídia/PNG, cancelamento seguro, integridade de cache e verificação final continuam ativos. O que foi removido é o uso de medições de headroom para limitar antecipadamente a quantidade de trabalho.
