# coding=utf-8
# 导入蓝图对象
from . import api
from flask import request,jsonify, current_app, session, g
from ihome.utils.response_code import RET
import re
# 导入模型类
from ihome.models import User
# 导入数据库实例
from ihome import db, constants
# 导入登录验证码装饰器
from ihome.utils.commons import login_required
# 导入七牛云接口
from ihome.utils.image_storage import storage




@api.route('/sessions',methods=['POST'])
def login():
    """
    用户登录,获取参数,校验参数,查询数据,返回结果
    1/获取参数,mobile,password,get_json()
    2/校验参数存在
    3/进一步获取详细的参数信息
    4/校验参数完善性
    5/校验手机号格式,re
    6/校验密码,首先查询数据库,保存查询结果.校验
    7/校验密码和手机号
    8/返回登录结果.user.id,name,mobile
    9/返回登录结果,user.id
    :return:
    """
    # 获取参数
    user_data = request.get_json()
    # 校验参数
    if not user_data:
        return jsonify(errno=RET.PARAMERR, errmsg="参数错误")
    # 获取详细的参数信息
    mobile = user_data.get("mobile")
    password = user_data.get('password')
    # 校验参数的完整性
    if not all([mobile,password]):
        return jsonify(errno=RET.PARAMERR, errmsg="参数缺失")
    # 校验手机号
    if not re.match(r'^1[34578]\d{9}$', mobile):
        return jsonify(errno=RET.DATAERR, errmsg="手机号格式错误")
    # 校验密码,需要查询数据库
    try:
        user = User.query.filter_by(mobile=mobile).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="查询用户信息失败")
    # 校验查询结果
    if user is None or not user.check_password(password):
        return jsonify(errno=RET.DATAERR, errmsg="手机号或密码错误")
    # 缓存用户信息
    session["user_id"] = user.id
    session["name"] = mobile
    session["mobile"] = mobile
    # 返回查询结果
    return jsonify(errno=RET.OK, errmsg="OK", data={"user_id":user.id})


@api.route("/session", methods=['DELETE'])
@login_required
def logout():
    """退出登录"""
    # 清除用户缓存信息
    session.clear()
    return jsonify(errno=RET.OK, errmsg="OK")


@api.route('/user', methods=['GET'])
@login_required
def get_user_profile():
    """
    获取用户信息
    1/获取参数,用户id
    2/根据用户进行查询数据库
    3/校验查询结果
    4/返回前端数据.user.to_dict()
    :return:
    """
    # 通过登录验证码装饰器实现的逻辑,使用g变量获取用户id
    user_id = g.user_id
    # 根据id查询数据库
    try:
        user = User.query.filter_by(id=user_id).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg="获取用户信息失败")
    # 校验查询结果
    if user is None:
        return jsonify(errno=RET.DATAERR, errmsg="获取用户信息失败")
    return jsonify(errno=RET.OK, errmsg="OK", data=user.to_dict())


@api.route('/user/name', methods=['PUT'])
@login_required
def change_user_name():
    """
    修改用户名
    1/获取用户信息,
    2/获取参数,json数据,name字段修改后的用户名信息
    3/校验参数
    4/根据用户id,查询数据库,更新用户信息,本质是插入数据
    5/更新缓存信息
    6/返回结果data={'name':name}
    :return:
    """
    # 获取用户id
    user_id = g.user_id
    # 获取用户输入的参数,name
    user_data = request.get_json()
    # 校验参数
    if not user_data:
        return jsonify(errno=RET.PARAMERR, errmsg="参数错误")
    # 获取详细的参数信息
    name = user_data.get('name')
    # 校验参数
    if not name:
        return jsonify(errno=RET.PARAMERR, errmsg="用户名称不能为空")
    # 保存数据
    try:
        # 使用update跟新用户信息
        User.query.filter_by(id=user_id).update({"name":name})
        # 提交数据
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        # 提交数据发生异常,需要进行回滚
        db.session.rollback()
        return jsonify(errno=RET.DBERR, errmsg="更新用户信息失败")
    # 更新缓存信息
    session["name"] = name
    # 返回结果
    return jsonify(errno=RET.OK, errmsg="OK", data={"name":name})


@api.route('/user/avatar', methods=['POST'])
@login_required
def save_user_avatar():
    """
    保存用户头像
    1/获取用户id,g变量
    2/获取图片参数,avatar = request.files.get("avatar")
    3/读取图片数据,ava_data = avatar.read()
    4/调用七牛云接口,上传用户头像,保存结果,七牛云对图片计算后的名称
    5/保存图片的url,相对路径,image_name
    6/拼接图片的完整路径,constants的七牛云外链域名+调用七牛云接口返回的图片名称
    7/返回结果
    :return:
    """
    # 获取用户信息
    user_id = g.user_id
    # 获取图片数据
    avatar = request.files.get("avatar")
    # 校验参数
    if not avatar:
        return jsonify(errno=RET.PARAMERR,errmsg="未上传用户头像")
    # 读取图片数据
    avatar_data = avatar.read()
    # 调用七牛云
    try:
        # 调用七牛云接口会返回图片的名称,即外链域名后面的相对路径
        image_name = storage(avatar_data)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.THIRDERR,errmsg="上传用户头像失败")
    # 保存头像数据到数据库
    try:
        User.query.filter_by(id=user_id).update({"avatar_url":image_name})
        # 提交数据
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        # 保存数据发生异常,进行回滚
        db.session.rollback()
        return jsonify(errno=RET.DBERR, errmsg="保存头像数据失败")
    # 拼接用户头像的完整url
    image_url = constants.QINIU_DOMIN_PREFIX + image_name
    # 返回结果
    return jsonify(errno=RET.OK, errmsg="OK", data={"avatar_url":image_url})


@api.route('/user/auth',methods=['POST'])
@login_required
def set_user_auth():
    """
    设置用户实名信息
    1/获取用户变量id,g变量
    2/获取post请求的参数,get_json(),校验参数
    3/获取real_name 和 id_cart参数
    4/校验参数完整性
    5/保存用户输入的实名信息,确保用户实名信息为空
    6/返回结果
    :return:
    """

    # 获取用户id
    user_id = g.user_id
    # 获取post请求的参数
    user_data = request.get_json()
    # 校验参数
    if not user_data:
        return jsonify(erron=RET.PARAMERR,errmsg="参数错误")
    # 获取详细的参数信息
    real_name = user_data.get("real_name")
    id_card = user_data.get("id_card")
    # 校验参数完整性
    if not all([real_name,id_card]):
        return jsonify(errno=RET.PARAMERR, errmsg="参数缺失")
    # 保存用户的认证信息
    try:
        # 查询用户信息,更新用户实名信息需要确保实名数据为空
        User.query.filter_by(id=user_id, real_name=None,id_card=None).update({"real_name":real_name,"id_card":id_card})
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR, errmsg="保存用户实名信息失败")
    # 返回结果
    return jsonify(errno=RET.OK, errmsg="OK")

@api.route('/user/auth', methods=['GET'])
@login_required
def get_user_auth():
    """
    获取用户实名信息
    1/获取用户id,g变量
    2/根据用户id查询数据库
    3/校验查询结果,无效操作
    4/返回结果,user.auth_to_dict()
    :return:
    """
    # 获取用户id
    user_id = g.user_id
    # 查询数据库
    try:
        user = User.query.filter_by(id=user_id).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="查询实名信息失败")
    if user is None:
        return jsonify(errno=RET.DATAERR, errmsg="无效操作")
    # 返回实名信息
    return jsonify(errno=RET.OK,errmsg="OK",data=user.auth_to_dict())










