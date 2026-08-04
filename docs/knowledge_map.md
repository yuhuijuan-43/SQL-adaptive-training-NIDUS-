# viz-standalone.html 节点树

## 第 0 层 — 根节点

```
root [SQL知识图谱]
```

## 第 1 层 — 一级分类

```
root
├─ top-255 [DML]
├─ top-257 [DDL]
├─ top-256 [函数]
├─ top-264 [表连接]
├─ top-265 [约束]
├─ top-266 [子查询]
└─ top-273 [SELECT]
```

## 第 2 层 — 二级分类（子节点）

```
top-255 [DML]
├─ cat-2748 [SELECT]
├─ cat-2749 [INSERT]
├─ cat-2750 [UPDATE]
└─ cat-2751 [DELETE]

top-257 [DDL]
├─ cat-2774 [CREATE]
├─ cat-2781 [ALTER]
├─ cat-2776 [DROP]
├─ cat-2777 [TRUNCATE]
├─ cat-2778 [RENAME]
└─ cat-2779 [COMMENT]

top-256 [函数]
├─ cat-2760 [字符串函数]
├─ cat-2764 [数字函数]
├─ cat-2766 [聚合函数]
├─ cat-2769 [转换函数]
└─ cat-2771 [窗口函数]

top-264 [表连接]
├─ cat-2786 [内连接]
├─ cat-2787 [外连接]
├─ cat-2788 [自连接]
└─ cat-2789 [交叉连接]

top-265 [约束]
├─ cat-275 [主键]
└─ cat-276 [外键]

top-266 [子查询]
├─ cat-2791 [标量子查询]
├─ cat-2792 [列子查询]
├─ cat-2793 [表子查询]
└─ cat-2794 [IN 子查询]

top-273 [SELECT]
├─ cat-2795 [基本 SELECT：字段、别名、常量]
├─ cat-2796 [WHERE 条件筛选]
├─ cat-2797 [聚合函数与 GROUP BY]
└─ cat-2798 [HAVING 子句]
```

## 统计

| 层级 | 节点数 |
|------|--------|
| 第 0 层（根） | 1 |
| 第 1 层（一级分类） | 7 |
| 第 2 层（二级分类） | 29 |
| 合计 | 37 |