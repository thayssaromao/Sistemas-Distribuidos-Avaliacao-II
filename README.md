# Sistemas-Distribuidos-Avaliacao-II
Microsserviços, Sistema de Mensageria, Criptografia de Chave  Assimétrica

A *Exchange* é um agente de mensagens. Ela recebe mensagens do seu produtor (ex: MS Gateway) e as empurra para as Queues. Ela não armazena mensagens; ela apenas decide para onde elas devem ir com base em regras chamadas Bindings (ligações).

*Exchange Escolhida: Topic*

# Routing Keys
A Routing Key é um "atributo" ou "etiqueta" que o produtor anexa à mensagem. Ela descreve o conteúdo da mensagem.

- promotion.received
- promotion.vote
- promotion.published
- promotion.highlight
- promotion.[category]