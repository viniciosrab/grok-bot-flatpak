# Triagem dos achados principais

Este relatório classifica os oito pontos levantados em `Achados principais.md` com base no código, nos testes, nos contratos atuais do repositório e na documentação do Electron.

## Resumo executivo

| # | Achado | Classificação | Decisão |
|---|---|---|---|
| 1 | `--password-store=basic` | Trade-off real e proposital | Não remover sem alternativa comprovada |
| 2 | `app.relaunch()` seguido de `app.exit()` | Trade-off proposital; processo órfão não comprovado | Não alterar sem teste de runtime |
| 3 | Testes C++ duplicam a implementação | Problema arquitetural real — corrigido | Helpers compartilhados extraídos; PID, UID e GID verificados |
| 4 | Fallback estrutural do ASAR | Risco real — corrigido | Anchors exatos automáticos; fallback manual, restrito e auditável |
| 5 | Deep link pode falhar e retornar sucesso | Bug real — corrigido | Falha de encaminhamento retorna `1`; ausência de URL retorna `0` |
| 6 | Proteção da branch `main` | Não verificável localmente | Exige auditoria autorizada do ruleset remoto |
| 7 | `KF6WindowSystem` aparentemente desnecessário | Falso positivo sob o contrato atual | Não remover |
| 8 | Versão do companion diferente da versão do payload | Ambiguidade de manutenção — documentada | Política independente registrada em `CONTRIBUTING.md` |

## Resultados implementados

### 1. Falha no encaminhamento de deep links — implementado e verificado

**Classificação:** bug real e prioritário.

`forwardProtocolUrls()` consegue informar falha, mas o caminho executado quando uma segunda instância perde o lock ignora esse resultado e encerra com código `0`.

Consequência observável:

1. uma segunda instância recebe uma URL `grokbot:` ou `sand:`;
2. o encaminhamento ao Electron falha;
3. a URL não é entregue;
4. o companion informa sucesso ao chamador.

**Evidência:**

- `companion/src/main.cpp:143-152` — `forwardProtocolUrls()` retorna `false` quando `QProcess::startDetached()` falha;
- `companion/src/main.cpp:424-429` — o caminho de lock perdido agora converte a falha em código de saída `1` somente quando há URL;
- `companion/tests/test_deep_link_exit.cpp` — teste comportamental no executável real, com lock ocupado e comando inválido.

**Implementação:** o caminho de lock perdido agora retorna `1` quando há URLs e `forwardProtocolUrls()` falha. Sem URL, o caminho continua retornando `0`.

**Verificação:** `companion_deep_link_exit` mantém o mesmo `QLockFile` ocupado, inicia o executável real com um comando Electron inválido e verifica `1` com URL e `0` sem URL. O caso está registrado no CTest e passou no gate completo.

### 2. Fallback estrutural do ASAR — implementado e verificado

**Classificação:** risco real, corrigido e verificado.

O patch continua exigindo exatamente uma ocorrência semântica e falha quando encontra zero, múltiplos candidatos ou formas aproximadas inválidas. A regra de controles também identifica o membro pretendido para o fallback estrutural.

**Evidência:**

- `tools/patch_electron_native_frame.py` — pares exatos para o payload pinado atual, seleção por caminho conhecido e fallback estrutural opt-in;
- `_apply_native_frame_rules()` — falha automática quando só existe uma forma estrutural não pinada;
- `io.github.viniciosrab.GrokBot.yml` — o fluxo automático chama o helper sem `--allow-structural-fallback`;
- `tests/test_electron_native_frame.py` — cobertura do payload atual, formato futuro, auditoria manual e decoys `index-copy.js`/`index-*`.

**Implementação:** o payload atual usa pares byte-exatos ancorados nos membros pinados, incluindo `index-C57MhV1e.js` e `index-B7CuLxVI.js`. Uma alteração futura de minificação falha até que novos anchors sejam revisados e adicionados. O fallback estrutural continua disponível apenas para diagnóstico manual, somente no caminho renderer conhecido; `index-copy.js`, outros `index-*` e assets não relacionados nunca são candidatos automáticos.

A CLI exige `--allow-structural-fallback` para gravar um patch que usou fallback e imprime cada regra e membro afetados. O manifest não passa essa opção: a embalagem normal só aceita os anchors exatos pinados. A indentação do bloco shell também foi normalizada para manter o contrato YAML legível e estável.

**Verificação:** os testes Python cobrem os anchors exatos atuais, a falha de formato futuro sem aprovação, a auditoria da CLI, a preservação do arquivo quando a aprovação falta e ASARs adversariais com `index-copy.js`, outros `index-*` e `unrelated.js`. O conjunto de 265 testes Python e os nove testes CTest passaram dentro de `org.kde.Sdk//6.11`.

## Refatoração realizada

### 3. Testes C++ não executam os mesmos helpers de produção — implementado e verificado

**Classificação:** problema arquitetural real, sem bug funcional atualmente demonstrado.

Antes da correção, `companion_lifecycle_posix` era compilado apenas com `test_lifecycle_posix.cpp`, que continha implementações espelhadas. Agora os probes continuam exercitando sockets Unix, `SO_PEERCRED` e processos reais, mas chamam o mesmo módulo compilado no companion.

**Evidência:**

- `companion/src/lifecycle_helpers.cpp` e `.h` — módulo compartilhado com interface pequena;
- `companion/CMakeLists.txt` — módulo ligado ao executável de produção;
- `companion/tests/CMakeLists.txt` — módulo ligado ao alvo CTest.

**Implementação:** `companion/src/lifecycle_helpers.cpp` e `.h` agora contêm apenas os helpers de protocolo, sockets, credenciais, grupos de processos e decisões Show/Quit que eram duplicados. `LinuxPeerCredentials` expõe PID, UID e GID a partir da mesma chamada `SO_PEERCRED`; `linuxPeerPid()` delega a essa implementação. O módulo é compilado e ligado ao companion e ao alvo CTest; não foram extraídos UI Qt nem adapters.

**Verificação:** os probes POSIX usam o mesmo módulo de produção, validam PID, UID e GID do peer real e o CTest registrou nove testes, todos aprovados no SDK.

## Comportamentos propositais que não devem ser alterados

### 4. `--password-store=basic`

**Classificação:** redução real de proteção em repouso, aceita como solução de compatibilidade.

O Electron seleciona o backend `basic_text` quando recebe `--password-store=basic`. Entretanto, essa opção foi introduzida porque KWallet não estava disponível dentro do sandbox e os cookies protegidos pelo OSCrypt não podiam ser recuperados após reiniciar o aplicativo.

Não existe evidência local suficiente para afirmar que tokens ou credenciais do Grok estejam atualmente expostos. Remover a opção sem uma integração funcional equivalente restauraria um problema conhecido de persistência do login.

**Decisão:** não remover até existir e ser testada uma alternativa baseada em KWallet, libsecret ou Secret Portal que funcione dentro do Flatpak.

### 5. Relaunch com `app.exit()`

**Classificação:** trade-off proposital; risco de daemon órfão ainda não reproduzido.

O Electron confirma que `app.exit()` não emite `before-quit` nem `will-quit`. Porém, o código vendor intercepta `app.quit()` durante o drain do daemon e impede que o relaunch de aceleração gráfica termine a instância antiga. A troca para `app.exit()` foi feita para permitir que o relaunch ocorra.

Portanto, substituir diretamente `exit()` por `quit()` quebraria novamente o relaunch. A possibilidade de deixar um daemon antigo vivo é plausível, mas ainda não foi demonstrada por um teste de runtime.

**Decisão:** não alterar o fluxo atual sem uma solução que preserve simultaneamente o relaunch e o cleanup.

**Teste necessário:** registrar o PID do daemon, provocar o relaunch de GPU, verificar que o processo antigo desapareceu e confirmar que existe no máximo um daemon associado à nova instância.

### 6. Dependência de `KF6WindowSystem`

**Classificação:** falso positivo sob o contrato atual.

Não há link direto para `KF6::WindowSystem`, mas `companion/CMakeLists.txt:11-14` declara explicitamente que `KF6WindowSystem` é uma dependência obrigatória e que sua ausência deve interromper o build. O workspace gate e a configuração de CI também incorporam essa expectativa.

Ausência de uso direto não prova que a dependência esteja sobrando quando o contrato do projeto deliberadamente a utiliza como requisito fail-closed.

**Decisão:** não remover sem uma decisão explícita de alterar o contrato e sem validar o build completo no `org.kde.Sdk//6.11`.

## Resultado documentado

### 7. Versão do companion e versão do payload — documentado e verificado

**Classificação:** ambiguidade de manutenção, não bug funcional.

O companion declara versão `0.47.0`, enquanto o payload está em `0.51.0`. Não foi encontrado uso funcional de `PROJECT_VERSION`, portanto a diferença não demonstra comportamento incorreto.

**Implementação:** `CONTRIBUTING.md` documenta que o companion possui versionamento independente, explica sua finalidade e define quando atualizar o companion ou o payload. Nenhuma versão foi sincronizada e nenhum payload foi alterado por esse motivo.

**Verificação:** a documentação foi adicionada à seção técnica de releases e o conjunto completo de testes passou.

## Item não verificável localmente

### 8. Ruleset da branch `main`

**Classificação:** alegação não confirmada nesta auditoria.

O repositório local contém workflows e documentação do fluxo de contribuição, mas não contém um snapshot autoritativo das configurações do ruleset remoto. Assim, não é possível provar localmente os valores de:

- `dismiss_stale_reviews_on_push`;
- `require_last_push_approval`;
- associação dos checks obrigatórios a um `integration_id`.

Essas configurações podem merecer endurecimento, mas exigem uma consulta remota explicitamente autorizada antes de qualquer conclusão.

## Resultados implementados nesta sessão

1. Código de saída de deep links corrigido e coberto no seam executável real.
2. Fallback estrutural do ASAR restrito a diagnóstico manual; embalagem automática usa anchors exatos pinados.
3. Helpers de lifecycle compartilhados entre produção e CTest, com PID/UID/GID cobertos.
4. Indentação do bloco de patch no manifest corrigida.
5. Política de versionamento independente do companion documentada.

Não alterar `--password-store=basic`, o fluxo `app.relaunch()`/`app.exit()` ou a exigência de `KF6WindowSystem` sem substituições comprovadamente equivalentes.
