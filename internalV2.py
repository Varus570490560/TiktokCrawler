import tkinter

button_width: int = 80
button_height: int = 20


root_windows: tkinter.Tk
crawl_button: tkinter.Button
import_xlsx_button: tkinter.Button

pixel_virtual: tkinter.PhotoImage


def render_ui():

    global button_height
    global button_width

    global root_windows
    global crawl_button
    global import_xlsx_button

    global pixel_virtual

    root_windows = tkinter.Tk()
    root_windows.title("短视频播放量爬虫（0.0）")
    root_windows.geometry("500x314")

    pixel_virtual = tkinter.PhotoImage(width=1, height=1)

    crawl_button = tkinter.Button(root_windows,
                                  text="Begin crawl",
                                  height=button_height,
                                  width=button_width,
                                  image=pixel_virtual,
                                  compound="center")
    crawl_button.pack()




    root_windows.mainloop()


