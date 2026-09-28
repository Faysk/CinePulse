# CinePulse 1.2.26

A 1.2.26 promove o hotfix de confiabilidade do pipeline registrado em #113.

## Isolamento do teste do updater

O teste `test_portable_launch_binds_handoff_to_verified_pending_descriptor` substituía `cinepulse.update_manager.subprocess.Popen`. Como `subprocess` é um módulo compartilhado do Python, esse patch também podia interceptar processos disparados por outras rotinas concorrentes.

No Quality da 1.2.25, o runner Windows/Python 3.14.7 executou uma coleta NVIDIA por `nvidia-smi` durante o teste. O mock contou essa chamada junto com o handoff PowerShell real e falhou com duas chamadas observadas, embora o updater tivesse iniciado somente um handoff.

Agora o teste substitui a referência `subprocess` somente dentro de `cinepulse.update_manager` e continua exigindo exatamente uma chamada a `Popen` do updater. O contrato permanece forte sem depender do que o runner esteja executando em paralelo.

## Impacto

- nenhuma mudança funcional na lógica runtime do updater;
- elimina interferência de telemetria/processos concorrentes no teste;
- revalida o mesmo matrix cell Windows/Python 3.14.7 que expôs a regressão;
- mantém Quality, Recovery e os gates de release como autoridade para publicação.

Closes #113.

A aceitação física NVIDIA/8K/120 permanece acompanhada separadamente em #4.
