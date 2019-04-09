#from symbolic.args import symbolic

#@symbolic(in1="foo", in2="cccdd")
def mytest(in1, in2):
    if in1 ==  0:
        in1 = in1 + 3
        if in1 < in2:
            return 0
    elif in1 == 1:
        in1 = in1 - in2 
        if in1 < in2:
            return 1
    else:
        return 9
    
    return 10
