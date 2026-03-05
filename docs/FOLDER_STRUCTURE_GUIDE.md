# 知识库文件夹结构指南

本文档说明如何组织 `data/raw` 目录，以便 Agent 能准确识别文档来源。

## 📁 推荐目录结构

```
data/raw/
├── RK3506/                   # 芯片/产品类别
│   ├── uboot/               # 子类别
│   │   ├── README.md
│   │   └── build_guide.pdf
│   ├── kernel/
│   │   └── config_guide.docx
│   └── sdk/
│       └── quick_start.md
│
├── PX30/                     # 另一个芯片类别
│   ├── uboot/
│   │   └── README.md
│   └── kernel/
│       └── porting_guide.md
│
├── SSD212/                   # 第三个芯片类别
│   └── datasheet/
│       └── SSD212_Datasheet.pdf
│
├── 福利制度文档/              # 其他类别（中文也支持）
│   ├── 年假制度.md
│   └── 报销流程.pdf
│
├── cmake/                    # 通用工具文档
│   └── tutorial.md
│
├── buildroot/
│   └── guide.pdf
│
└── README.md                 # 根目录下的通用文档
```

## 🎯 关键设计原则

### 1. 一级目录 = 主要分类
- 每个一级目录代表一个**独立的分类**
- Agent 通过分类快速定位相关文档
- 例如：`RK3506/`、`PX30/`、`福利制度文档/`

### 2. 支持多级子目录
- 可以有多层子目录组织文档
- 例如：`RK3506/uboot/build_guide.pdf`
- 子目录信息会作为 `subcategory` 元数据保存

### 3. 根目录文件
- 直接在 `data/raw/` 下的文件属于 `root` 分类
- 适合放置通用文档，如 `README.md`

## 🔍 Agent 如何利用这个结构

### 场景 1: 查找特定芯片文档

```
用户：RK3506 的 uboot 怎么编译？

Agent 思考过程：
1. 调用 run_bash: ls data/raw/
   → 看到有 RK3506/, PX30/, SSD212/ 等目录
   
2. 调用 search_knowledge(query="RK3506 uboot 编译")
   → 收到结果：
      [1] 📁 RK3506/uboot/build_guide.pdf | 分类: RK3506/uboot
          相关度: 0.923
          内容: ...
          
3. Agent 确认这是 RK3506 的文档，不是 PX30 的
4. 给出准确答案
```

### 场景 2: 跨分类搜索

```
用户：所有芯片的 uboot 编译方法

Agent 思考过程：
1. 调用 search_knowledge(query="uboot 编译方法")
   → 收到结果：
      [1] 📁 RK3506/uboot/build_guide.pdf | 分类: RK3506/uboot
      [2] 📁 PX30/uboot/README.md | 分类: PX30/uboot
      [3] 📁 SSD212/uboot/guide.md | 分类: SSD212/uboot
      
      📊 涉及分类: RK3506, PX30, SSD212
      
2. Agent 看到来自三个不同芯片的文档
3. 分别总结每个芯片的编译方法
```

### 场景 3: 精确过滤

```
用户：SSD212 的资料

Agent 思考过程：
1. 调用 run_bash: find data/raw/SSD212 -type f
   → 列出所有 SSD212 目录下的文件
   
2. 或者调用 search_knowledge(query="SSD212")
   → 只返回 category=SSD212 的结果
```

## 📊 元数据结构

每个文档片段都会保存以下元数据：

```json
{
  "doc_id": "RK3506/uboot/build_guide.pdf",
  "category": "RK3506",
  "subcategory": "uboot",
  "full_path": "RK3506/uboot/build_guide.pdf",
  "section": "编译步骤",
  "chunk_index": 0,
  "is_subchunk": false
}
```

## 🛠️ 实际使用示例

### 示例 1: 技术文档库

```
data/raw/
├── RK3506/
│   ├── uboot/
│   ├── kernel/
│   ├── rootfs/
│   └── sdk/
├── PX30/
│   ├── uboot/
│   ├── kernel/
│   └── sdk/
├── 开发环境/
│   ├── docker/
│   ├── 交叉编译器/
│   └── 调试工具/
└── 常见问题/
    ├── 编译问题.md
    └── 烧录问题.md
```

### 示例 2: 企业知识库

```
data/raw/
├── 技术文档/
│   ├── API文档/
│   ├── 架构设计/
│   └── 部署手册/
├── 产品文档/
│   ├── 产品A/
│   ├── 产品B/
│   └── 产品C/
├── 管理制度/
│   ├── 人事制度/
│   ├── 财务制度/
│   └── 行政制度/
└── 培训资料/
    ├── 新员工培训/
    └── 技术培训/
```

### 示例 3: 混合类型

```
data/raw/
├── 芯片文档/
│   ├── RK3506/
│   ├── PX30/
│   └── SSD212/
├── 软件工具/
│   ├── cmake/
│   ├── buildroot/
│   └── yocto/
├── 项目文档/
│   ├── 项目A/
│   └── 项目B/
└── 通用参考/
    ├── Linux命令大全.pdf
    ├── Git使用指南.md
    └── 编码规范.md
```

## ✅ 最佳实践

### 1. 命名规范
- 使用有意义的目录名
- 避免特殊字符（除了 `-` 和 `_`）
- 中文目录名完全支持

### 2. 分类粒度
- 一级目录建议 5-15 个，太多会分散
- 每个分类下可以有多层子目录
- 相关文档放在同一分类下

### 3. 文档命名
- 文件名要有描述性
- 例如：`build_guide.pdf` 比 `doc1.pdf` 好
- 版本号可以放在文件名中：`API_v2.0.md`

### 4. 避免的问题
- ❌ 不要所有文件都堆在根目录
- ❌ 不要创建太深的目录层级（建议不超过 4 层）
- ❌ 不要在不同分类放重复内容

## 🔧 处理流程

当你运行 `python scripts/ingest_folder.py` 时：

1. **递归扫描** `data/raw/` 及其所有子目录
2. **提取路径信息** 为每个文件生成 category 和 subcategory
3. **转换文档** 保留目录结构保存到 `data/canonical_md/`
4. **智能切片** 每个 chunk 都携带完整的路径元数据
5. **向量化存储** 元数据随向量一起存入 Qdrant

## 📈 效果展示

### RAG 检索结果示例

```
找到 3 条相关结果:
📊 涉及分类: RK3506, PX30

[1] 📁 RK3506/uboot/build_guide.pdf | 分类: RK3506/uboot | 章节: 编译步骤
   相关度: 0.923
   内容:
   编译 RK3506 的 uboot 需要以下步骤...
   
---
[2] 📁 PX30/uboot/README.md | 分类: PX30/uboot | 章节: 快速开始
   相关度: 0.856
   内容:
   PX30 的 uboot 编译与 RK3506 类似，但需要注意...
   
---
[3] 📁 RK3506/kernel/config.md | 分类: RK3506/kernel | 章节: 默认配置
   相关度: 0.742
   内容:
   内核配置与 uboot 编译有关联...
```

## 🎓 总结

你的构想非常合理！通过：

1. ✅ **保留文件夹结构** - 不拍扁，信息不丢失
2. ✅ **doc_id 使用相对路径** - 如 `RK3506/uboot/README.md`
3. ✅ **丰富的元数据** - category, subcategory, full_path
4. ✅ **RAG 结果展示路径** - Agent 一眼看出来源

Agent 就能：
- 快速理解文档组织结构
- 准确识别文档来源
- 避免混淆不同分类的内容
- 支持跨分类和精确过滤搜索

**无需修改 Agent 提示词**，LLM 通过 ls 命令和 RAG 结果中的路径信息，自己就能理解整个知识库的结构！
