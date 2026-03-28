from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """
    所有输出 Schema 的基类。
    - JSON 序列化时自动 snake_case → camelCase
    - 反序列化时同时接受 snake_case 和 camelCase
    """
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,      # 允许用原字段名赋值
        from_attributes=True,       # 支持 ORM 对象直接转换
    )
