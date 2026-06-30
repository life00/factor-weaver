# Literature

## Research Gap

Deep reinforcement learning for portfolio management is well-studied, but no existing framework simultaneously integrates price, technical, fundamental, and behavioral (attention + sentiment) features in a single DRL model. Existing dynamic universe approaches either use a fixed set of assets or handle changes through event-driven additions, but not through periodic market-cap ranking with automatic transitions. Survivorship-bias-free backtesting in this context also remains under-addressed. This thesis develops an actor-critic framework combining multi-source features to determine portfolio weights under transaction costs on a rolling top-50 S&P500 universe, testing whether this integration yields superior risk-adjusted performance relative to standard benchmarks.

## Theory

- variable selection
  - fundamental
    - Yan & Zheng (2017): mines 18,000+ fundamental signals; used to justify inclusion of fundamental ratios in the state space
  - behavioral
    - attention
      - Vozlyublennaia (2014): Google search volume predicts short-term index returns; justifies Google search intensity as a feature
    - sentiment
      - Kirtac & Germano (2025): theoretical framing of financial sentiment and LLM-based measurement; provides the conceptual foundation
      - Dong et al. (2024): FNSPID dataset: 15.7M time-aligned news records across 4,775 S&P500 tickers; provides the data pipeline methodology
      - Benhenda (2025): relevant implementation using FinRL and FNSPID dataset
      - Ranade et al. (2026): time-decay mechanism for aging news, confidence-based aggregation; justifies the scoring and aggregation methodology
  - data sample / survivorship bias
    - Liu et al. (2022): identifies survivorship bias as a key challenge in DRL backtesting; provides framework for bias-aware environment construction
- RL assumptions
  - Schulman et al. (2017): PPO algorithm; foundation for the actor-critic architecture choice
- benchmarks
  - traditional models
    - Markowitz (1952): mean-variance foundation; baseline comparison
    - DeMiguel et al. (2009): 1/N often beats mean-variance out-of-sample due to estimation error (3,136 citations); establishes 1/N as the key benchmark
  - ML-based models
    - Nazareth & Reddy (2023): broad financial ML survey; positions thesis in the wider landscape
    - Sutiene et al. (2024): AI techniques for portfolio management; directly relevant framing

## Methodology

- training environment
  - stock selection / dynamic universe
    - Noguer I Alonso & Srivastava (2020): selects top 24 US equities and applies DRL with daily rebalancing; supports selecting a subset of a broad market for RL
    - Betancourt & Chen (2021): handles asset sets that change over time, with built-in transaction cost minimization; supports the dynamic aspect of a rolling universe
  - transaction costs
    - Zhang et al. (2020): cost-sensitive DRL portfolio; directly models transaction costs in the reward function
    - Almahdi & Yang (2017): RRL with transaction costs and maximum-drawdown-based reward (224 citations); compares Sharpe, Calmar, Sterling objectives under different cost scenarios
- behavioral feature integration
  - pre-computed LLM sentiment scores fed as RL state features
    - Kirtac & Germano (2024): pre-computed OPT sentiment scores achieve Sharpe 3.05, outperforming dictionary methods (1.23); validates the pre-compute approach
    - Mantshimuli (2025): FinBERT scores pre-computed and fed into DDPG DRL state space; confirms the offline-scores-to-RL pipeline beats all benchmarks
- model architecture
  - encoder
    - Xue & Ye (2025): cross-stock transformer attention to capture inter-asset correlations; attention mechanism provides built-in interpretability
  - RL type
    - Schulman et al. (2017): PPO; stable multi-epoch updates suited for continuous portfolio weight tasks
  - output
    - André & Coqueret (2020): Dirichlet distribution over the simplex enforces positive weights summing to one; addresses the no-short-selling constraint
  - reward function
    - Charkhestani & Esfahanipour (2026): incorporates loss aversion and overconfidence into RL reward; justifies risk-preference-adjusted Sharpe objectives
  - explainable AI
    - Xue & Ye (2025): attention weights reveal which stock interactions influenced each allocation decision; intrinsic explainability from the architecture
    - González-Cortés et al. (2024): transparent RL framework with explicit explanation of trading decisions; used if post-hoc XAI methods are needed
- evaluation
  - benchmarks
    - DeMiguel et al. (2009): 1/N as the hardest baseline
    - Espiga-Fernández et al. (2024): benchmarks DQN, DDPG, PPO, SAC across multiple market signals; provides comparison methodology

## Sources

- Almahdi, S., & Yang, S. Y. (2017). An adaptive portfolio trading system: A risk-return portfolio optimization using recurrent reinforcement learning with expected maximum drawdown. _Expert Systems with Applications_, _87_, 267-279. <https://doi.org/10.1016/j.eswa.2017.06.023>
- Noguer I Alonso, M., & Srivastava, S. (2020). Deep reinforcement learning for asset allocation in US equities. _SSRN_. <https://dx.doi.org/10.2139/ssrn.3711487>
- Betancourt, C., & Chen, W.-H. (2021). Deep reinforcement learning for portfolio management of markets with a dynamic number of assets. _Expert Systems with Applications_, _164_, 114002. <https://doi.org/10.1016/j.eswa.2020.114002>
- Bartram, S. M., Lohre, H., Pope, P. F., & Ranganathan, A. (2021). Navigating the factor zoo around the world: An institutional investor perspective. _Journal of Business Economics_, _91_(5), 655-703. <https://doi.org/10.1007/s11573-021-01035-y>
- Benhenda, M. (2025). FinRL-DeepSeek: LLM-Infused Risk-Sensitive Reinforcement Learning for Trading Agents. _arXiv_. <https://arxiv.org/abs/2502.07393>
- Charkhestani, A., & Esfahanipour, A. (2026). Behaviorally informed deep reinforcement learning for portfolio optimization with loss aversion and overconfidence. _Scientific Reports_, _16_(1). <https://doi.org/10.1038/s41598-026-35902-x>
- DeMiguel, V., Garlappi, L., & Uppal, R. (2009). Optimal Versus Naive Diversification: How Inefficient is the 1/N Portfolio Strategy? _Review of Financial Studies_, _22_(5), 1915-1953. <https://doi.org/10.1093/rfs/hhm075>
- André, E., & Coqueret, G. (2020). Dirichlet policies for reinforced factor portfolios. _arXiv:2011.05381_. <https://arxiv.org/abs/2011.05381>
- Dong, Z., Fan, X., & Peng, Z. (2024). FNSPID: A Comprehensive Financial News Dataset in Time Series. _arXiv:2402.06698_. <https://arxiv.org/abs/2402.06698>
- Espiga-Fernández, F., García-Sánchez, Á., & Ordieres-Meré, J. (2024). A systematic approach to portfolio optimization: A comparative study of reinforcement learning agents, market signals, and investment horizons. _Algorithms_, _17_(12), 570. <https://doi.org/10.3390/a17120570>
- González-Cortés, D., Onieva, E., Pastor, I., Trinchera, L., & Wu, J. (2024). Portfolio construction using explainable reinforcement learning. _Expert Systems_, _41_(11), e13667. <https://doi.org/10.1111/exsy.13667>
- Gunjan, A., & Bhattacharyya, S. (2022). A brief review of portfolio optimization techniques. _Artificial Intelligence Review_, _56_(5), 3847-3886. <https://doi.org/10.1007/s10462-022-10273-7>
- Kirtac, K., & Germano, G. (2024). Sentiment trading with large language models. _Finance Research Letters_, _62_, 105227. <https://doi.org/10.1016/j.frl.2024.105227>
- Kirtac, K., & Germano, G. (2025). Large language models in finance: what is financial sentiment? _arXiv:2503.03612_. <https://doi.org/10.48550/arXiv.2503.03612>
- Liu, X.-Y., Xia, Z., Rui, J., Gao, J., Yang, H., Zhu, M., Wang, C. D., Wang, Z., & Guo, J. (2022). FinRL-Meta: Market environments and benchmarks for data-driven financial reinforcement learning. _Advances in Neural Information Processing Systems_, _35_. <https://doi.org/10.48550/arXiv.2211.03107>
- Mantshimuli, L. (2025). Sentiment-Aware Portfolio Optimization: CVaR-Based Diversification With Deep Reinforcement Learning. _IEEE Access_. <https://doi.org/10.1109/access.2025.3624652>
- Markowitz, H. (1952). Portfolio Selection. _The Journal of Finance_, _7_(1), 77-91. <https://doi.org/10.1111/j.1540-6261.1952.tb01525.x>
- Nazareth, N., & Reddy, Y. V. R. (2023). Financial applications of machine learning: A literature review. _Expert Systems with Applications_, _219_, 119640. <https://doi.org/10.1016/j.eswa.2023.119640>
- Ranade, D. J., Bhaya, S., Bhimakari, S., Chan, M., Quille, K., & Jaiswal, R. (2026). On explaining the sentiments in prediction of stock movement: An XAI-based analysis. _Proceedings of the 2026 Conference on Human Centred Artificial Intelligence—Education and Practice_, 107–113. <https://doi.org/10.1145/3777490.3777510>
- Rezaei, M., & Nezamabadi-Pour, H. (2025). A taxonomy of literature reviews and experimental study of deep reinforcement learning in portfolio management. _Artificial Intelligence Review_, _58_(3). <https://doi.org/10.1007/s10462-024-11066-w>
- Schulman, J., Wolski, F., Dhariwal, P., Radford, A., & Klimov, O. (2017). Proximal Policy Optimization Algorithms. _arXiv:1707.06347_. <https://arxiv.org/abs/1707.06347>
- Sutiene, K., Schwendner, P., Sipos, C., Lorenzo, L., Mirchev, M., Lameski, P., Kabasinskas, A., Tidjani, C., Ozturkkal, B., & Cerneviciene, J. (2024). Enhancing portfolio management using artificial intelligence: Literature review. _Frontiers in Artificial Intelligence_, _7_, 1371502. <https://doi.org/10.3389/frai.2024.1371502>
- Vozlyublennaia, N. (2014). Investor attention, index performance, and return predictability. _Journal of Banking and Finance_, _41_, 17-35. <https://doi.org/10.1016/j.jbankfin.2013.12.010>
- Wang, Z., Huang, B., Tu, S., Zhang, K., & Xu, L. (2021). DeepTrader: A deep reinforcement learning approach for risk-return balanced portfolio management with market conditions embedding. _Proceedings of the AAAI Conference on Artificial Intelligence_, _35_(1), 643–650. <https://doi.org/10.1609/aaai.v35i1.16144>
- Xue, P., & Ye, Y. (2025). Attention-enhanced reinforcement learning for dynamic portfolio optimization. _Intelligent Systems with Applications_, _29_, 200622. <https://doi.org/10.1016/j.iswa.2025.200622>
- Yan, X., & Zheng, L. (2017). Fundamental Analysis and the Cross-Section of Stock Returns: A Data-Mining Approach. _Review of Financial Studies_, _30_(4), 1382-1423. <https://doi.org/10.1093/rfs/hhw001>
- Zhang, Y., Zhao, P., Wu, Q., Li, B., Huang, J., & Tan, M. (2020). Cost-sensitive portfolio selection via deep reinforcement learning. _IEEE Transactions on Knowledge and Data Engineering_, _34_(5), 2234-2248. <https://doi.org/10.1109/TKDE.2020.2979700>
